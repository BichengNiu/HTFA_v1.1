"""Conservative, replayable observed sea entries from continuously archived AIS.

The first sighting is a baseline, not an entry. Gaps, implausible jumps and
boundary jitter never create entries. Counts are observed AIS traffic, not a
claim that free receivers see every vessel in all four seas.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import math
from zoneinfo import ZoneInfo

from shapely.geometry import Point, shape
from shapely.prepared import prep

from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply.monitoring_cards import SEA_MONITORING_AREAS, change, fmt, windows

PROVIDER = "local-ais"
TZ = ZoneInfo("Asia/Shanghai")
MAX_GAP = timedelta(minutes=30)
MAX_SPEED_KNOTS = 60
POLL_GAP = timedelta(seconds=180)
BOUNDARY_MARGIN = 0.01  # ~1 km; deadband only, never a replacement sea boundary.


@lru_cache(maxsize=1)
def boundaries():
    document = data_store.read_json("data/sea_boundaries.geojson")
    definition = hashlib.sha256(data_store.encode([document, "entry-v1", BOUNDARY_MARGIN,
                                                  MAX_GAP.total_seconds(), MAX_SPEED_KNOTS]).encode()).hexdigest()
    polygons = {}
    for feature in document["features"]:
        sea = feature["properties"]["name_cn"]
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            raise ValueError("海域边界几何无效：" + sea)
        polygons[sea] = (prep(geometry.buffer(-BOUNDARY_MARGIN)), prep(geometry.buffer(BOUNDARY_MARGIN)))
    if set(polygons) != set(SEA_MONITORING_AREAS):
        raise ValueError("海域边界未完整覆盖四区")
    return definition, polygons


def start_collection(now=None):
    now = now or datetime.now(timezone.utc)
    definition, _ = boundaries()
    with data_store.connect() as conn:
        started = data_store.meta("local_collection_started_at", conn=conn)
        if not started:
            data_store.set_meta("local_collection_started_at", now.isoformat(), conn)
            data_store.set_meta("local_sea_definition", definition, conn)
        elif data_store.meta("local_sea_definition", conn=conn) != definition:
            raise ValueError("本地海域边界版本已变化；请显式迁移事件，不能混算")
    return started or now.isoformat()


def distance_nm(first, second):
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3440.065 * 2 * math.asin(math.sqrt(min(1, a)))


def infer_entries(points, polygons, checkpoint=None, include_state=False):
    """Replay a vessel's canonical, ordered positions; late arrival order is irrelevant."""
    checkpoint = checkpoint or {}
    state = dict(checkpoint.get("sides", {}))
    pending = {sea: (side, datetime.fromisoformat(stamp), datetime.fromisoformat(before))
               for sea, (side, stamp, before) in checkpoint.get("pending", {}).items()}
    events = []
    prior = checkpoint.get("previous")
    previous = (datetime.fromisoformat(prior[0]), prior[1], prior[2]) if prior else None
    for stamp, lat, lon, source in points:
        if previous and stamp <= previous[0]:
            continue
        valid_segment = previous is not None
        if previous:
            duration = stamp - previous[0]
            speed = distance_nm((previous[1], previous[2]), (lat, lon)) / (duration.total_seconds() / 3600)
            valid_segment = duration <= MAX_GAP and speed <= MAX_SPEED_KNOTS
        point = Point(lon, lat)
        for sea, (inner, outer) in polygons.items():
            classification = True if inner.contains(point) else False if not outer.contains(point) else None
            if not valid_segment:
                state[sea] = classification
                pending.pop(sea, None)
                continue
            if classification is None:
                # Preserve the stable side across the boundary deadband, but
                # confirmation still needs two consecutive stable-side points.
                pending.pop(sea, None)
                continue
            old = state.get(sea)
            if old is None or old == classification:
                state[sea] = classification
                pending.pop(sea, None)
                continue
            candidate = pending.get(sea)
            if candidate and candidate[0] == classification:
                if classification:
                    events.append((sea, candidate[1], {"before": candidate[2].isoformat(),
                                  "confirmed_at": stamp.isoformat(), "source": source,
                                  "method": "two stable observations; outside-to-inside"}))
                state[sea] = classification
                pending.pop(sea, None)
            else:
                pending[sea] = (classification, stamp, previous[0])
        previous = (stamp, lat, lon)
    if include_state:
        saved = {"sides": state, "pending": {sea: [side, stamp.isoformat(), before.isoformat()]
                                            for sea, (side, stamp, before) in pending.items()},
                 "previous": [previous[0].isoformat(), previous[1], previous[2]] if previous else None}
        return events, saved
    return events


def update_events(conn, changed):
    started = data_store.meta("local_collection_started_at", conn=conn)
    if not started:
        return
    definition, polygons = boundaries()
    if data_store.meta("local_sea_definition", conn=conn) != definition:
        raise ValueError("海域边界版本不一致，拒绝生成混合事件")
    for mmsi, earliest_new in sorted(changed.items()):
        saved = conn.execute("SELECT through_at,state FROM sea_vessel_checkpoints WHERE mmsi=? AND definition=? "
                             "AND through_at<? ORDER BY through_at DESC LIMIT 1",
                             (mmsi, definition, earliest_new)).fetchone()
        lower = saved[0] if saved else datetime.fromisoformat(started)
        state = json.loads(saved[1]) if saved else None
        operator = ">" if saved else ">="
        raw = conn.execute(f"SELECT observed,lat,lon,source FROM ais_positions WHERE mmsi=? AND observed{operator}? "
                           "ORDER BY observed,source", (mmsi, lower)).fetchall()
        # Same ship/time from two feeds is one observation. Conflicting positions
        # invalidate this timestamp instead of choosing the position that creates an entry.
        by_time = {}
        for stamp, lat, lon, source in raw:
            if lat is None or lon is None:
                continue
            by_time.setdefault(stamp, []).append((lat, lon, source))
        points = []
        for stamp, variants in sorted(by_time.items()):
            if all(distance_nm(variants[0][:2], row[:2]) <= 0.1 for row in variants):
                lat, lon, source = variants[0]
                points.append((stamp, lat, lon, source))
        events, current_state = infer_entries(points, polygons, state, include_state=True)
        conn.execute("DELETE FROM sea_entries WHERE provider=? AND definition=? AND mmsi=? "
                     "AND TRY_CAST(json_extract_string(evidence,'$.confirmed_at') AS TIMESTAMPTZ)>?",
                     (PROVIDER, definition, mmsi, lower))
        if events:
            conn.executemany("INSERT OR IGNORE INTO sea_entries VALUES (?,?,?,?,?,?,?)",
                             [(PROVIDER, definition, sea, mmsi, stamp, stamp.astimezone(TZ).date(), data_store.encode(evidence))
                              for sea, stamp, evidence in events])
        conn.execute("DELETE FROM sea_vessel_checkpoints WHERE mmsi=? AND definition=? AND through_at>?",
                     (mmsi, definition, lower))
        if current_state["previous"]:
            through = datetime.fromisoformat(current_state["previous"][0])
            conn.execute("INSERT OR REPLACE INTO sea_vessel_checkpoints VALUES (?,?,?,?,?)",
                         (mmsi, definition, through.astimezone(timezone.utc).date(), through, data_store.encode(current_state)))


def _continuous(conn, start, end):
    """Completeness of our sampling process, never completeness of world AIS coverage."""
    if end <= start:
        return False
    started = data_store.meta("local_collection_started_at", conn=conn)
    if not started or datetime.fromisoformat(started) > start:
        return False
    runs = conn.execute("SELECT started_at,status FROM collection_runs WHERE provider='Open Waters' "
                        "AND started_at>=? AND started_at<=? ORDER BY started_at",
                        (start - POLL_GAP, end)).fetchall()
    if not runs or runs[0][0] > start or runs[-1][0] < end - POLL_GAP:
        return False
    return all(status == "ok" for stamp, status in runs) and all(
        right[0] - left[0] <= POLL_GAP for left, right in zip(runs, runs[1:]))


def _count(conn, start, end):
    definition, _ = boundaries()
    return conn.execute("SELECT COUNT(*) FROM sea_entries WHERE provider=? AND definition=? "
                        "AND entered_at>=? AND entered_at<?", (PROVIDER, definition, start, end)).fetchone()[0]


def observation_summary(now=None):
    """Useful partial-month accumulation, with ratios gated on comparable coverage."""
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    with data_store.connect() as conn:
        started = data_store.meta("local_collection_started_at", conn=conn)
        if not started:
            return {"card": None, "rows": [], "source": None, "started_at": None}
        first = datetime.fromisoformat(started).astimezone(TZ)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        periods = windows(now.date())
        week_counts = []
        for start, end in periods[:2]:
            lower = datetime.combine(start, time.min, TZ)
            upper = datetime.combine(end + timedelta(days=1), time.min, TZ)
            week_counts.append(_count(conn, lower, upper) if _continuous(conn, lower, upper) else None)
        valid_run = conn.execute("SELECT COUNT(*) FROM collection_runs WHERE provider='Open Waters' "
                                 "AND status IN ('ok','partial') AND started_at>=? AND started_at<=?", (month_start, now)).fetchone()[0]
        month = _count(conn, max(first, month_start), now) if valid_run else None
        comparisons = [None, None]
        if _continuous(conn, month_start, now):
            for i, (lower_day, upper_day) in enumerate(periods[3:]):
                lower = datetime.combine(lower_day, time.min, TZ)
                upper = datetime.combine(upper_day, now.timetz().replace(tzinfo=None), TZ)
                if _continuous(conn, lower, upper):
                    comparisons[i] = _count(conn, lower, upper)
        card = ('海域监测', '4个',
                f'上周累计通过{fmt(week_counts[0])}艘次（环比 {change(*week_counts)}）',
                f'本月已记录通过{fmt(month)}艘次（环比 {change(month, comparisons[0])}，同比 {change(month, comparisons[1])}）')
        rows = []
        day = max(first.date(), now.date().replace(day=1))
        while day <= now.date():
            lower = datetime.combine(day, time.min, TZ)
            upper = min(datetime.combine(day + timedelta(days=1), time.min, TZ), now)
            observed = dict(conn.execute("SELECT sea,COUNT(*) FROM sea_entries WHERE provider=? AND entered_at>=? "
                                         "AND entered_at<? GROUP BY sea", (PROVIDER, lower, upper)).fetchall())
            quality = "观测期完整" if _continuous(conn, lower, upper) else "观测期不完整"
            for sea in SEA_MONITORING_AREAS:
                rows.append({"sea": sea, "date": day.isoformat(), "passages": observed.get(sea, 0) if valid_run else None,
                             "coverage": quality, "basis": "已确认的观测进入事件"})
            day += timedelta(days=1)
    return {"card": card, "rows": rows, "source": "本地AIS连续观测", "started_at": started}
