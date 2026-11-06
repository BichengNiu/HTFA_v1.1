"""Observed AIS reports only: persistent archive and bounded recent backfill."""
from __future__ import annotations

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from htfa.monitoring.energy_supply import ais
from htfa.monitoring.energy_supply import data_store


def archive_path() -> Path:
    return data_store.database_path()


@contextmanager
def connect_archive():
    """All AIS reads and writes share the project's one DuckDB transaction."""
    with data_store.connect() as conn:
        yield conn


def normalize_report(row: dict) -> dict:
    """Keep source observation time distinct from collector receipt time."""
    mmsi = ais.parse_integer(row.get("mmsi", row.get("MMSI")))
    observed = ais.parse_utc(
        row.get("observed_at", row.get("AIS报告时间 UTC")))
    # Preserve explicit historical imports; current live rows include a source
    # label and therefore must provide an observed_at value.
    if observed is None and not row.get("data_source"):
        observed = ais.parse_utc(row.get("received_at"))
    received = ais.parse_utc(
        row.get("received_at", row.get("采集器接收时间 UTC"))) or ais.utc_now()
    lat = ais.parse_number(row.get("lat", row.get("纬度")))
    lon = ais.parse_number(row.get("lon", row.get("经度")))
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        raise ValueError("MMSI无效")
    if observed is None or observed > ais.utc_now() + timedelta(minutes=5):
        raise ValueError("AIS报告时间缺失、无效或在未来")
    if not ais.valid_coordinate(lat, lon) or not ais.in_collection_area(lat, lon):
        raise ValueError("坐标无效或不在监测水域及边界观测带")
    category = row.get("category") or next((key for key, label in ais.VESSEL_TYPE_LABELS.items()
                                           if label == row.get("船型")), "unknown")
    if category not in ais.VESSEL_TYPE_LABELS:
        category = "unknown"
    sog = ais.parse_number(row.get("sog", row.get("航速 节")))
    course = ais.parse_number(row.get("course", row.get("航向 °")))
    if sog is not None and not 0 <= sog < 102.3:
        sog = None
    if course is not None and not 0 <= course < 360:
        course = None
    source = row.get("source") or row.get("data_source") or row.get("数据源")
    if not source:
        raise ValueError("需要提供原始数据源")
    return {**row, "mmsi": str(mmsi), "observed_at": observed.isoformat(),
            "received_at": received.isoformat(),
            "provider_received_at": row.get("provider_received_at", row.get("采集器接收时间 UTC")),
            "lat": lat, "lon": lon, "region": ais.region_for(lat, lon),
            "name": row.get("name", row.get("船名")),
            "imo": row.get("imo", row.get("IMO")),
            "sog": sog, "course": course, "moving": (sog or 0) >= 0.5,
            "category": category, "category_label": ais.VESSEL_TYPE_LABELS[category],
            "navigation_status": row.get("navigation_status", row.get("航行状态")),
            "destination": row.get("destination", row.get("目的地")),
            "draught": row.get("draught", row.get("吃水 米")),
            "source": str(source), "data_source": row.get("data_source", str(source)),
            "source_url": row.get("source_url", row.get("来源")),
            "age_minutes": None}


def archive_reports(rows: list[dict]) -> int:
    rows_with_observation_time = [
        row for row in rows
        if row.get("observed_at") or row.get("AIS报告时间 UTC")
        or not row.get("data_source")
    ]
    normalized = [normalize_report(row) for row in rows_with_observation_time]
    if not normalized:
        return 0
    with connect_archive() as conn:
        conn.execute("CREATE TEMP TABLE incoming_reports AS SELECT * FROM ais_reports LIMIT 0")
        conn.executemany("INSERT INTO incoming_reports VALUES (?, ?, ?, ?)",
                         [(row["mmsi"], row["observed_at"], row["source"],
                           json.dumps(row, ensure_ascii=False)) for row in normalized])
        inserted_rows = conn.execute("INSERT OR IGNORE INTO ais_reports SELECT * FROM incoming_reports "
                                     "RETURNING mmsi,observed").fetchall()
        # Static metadata can arrive again with the same observation key. Enrich
        # those reports without inventing new positions or increasing counts.
        updated = conn.execute("""
            UPDATE ais_reports AS stored
            SET payload=json_merge_patch(stored.payload, json_object(
                'flag',json_extract_string(incoming.payload,'$.flag'),
                'flag_country',json_extract_string(incoming.payload,'$.flag_country'),
                'flag_source',json_extract_string(incoming.payload,'$.flag_source')))
            FROM incoming_reports AS incoming
            WHERE stored.mmsi=incoming.mmsi AND stored.observed=incoming.observed
              AND stored.source=incoming.source
              AND json_extract_string(incoming.payload,'$.flag') IS NOT NULL
              AND (json_extract_string(stored.payload,'$.flag') IS DISTINCT FROM
                   json_extract_string(incoming.payload,'$.flag') OR
                   json_extract_string(stored.payload,'$.flag_country') IS DISTINCT FROM
                   json_extract_string(incoming.payload,'$.flag_country'))
            RETURNING stored.mmsi
        """).fetchall()
        conn.execute("DROP TABLE incoming_reports")
        inserted = len(inserted_rows)
        if inserted or updated:
            data_store.bump_revision("ais", conn)
        if inserted:
            from htfa.monitoring.energy_supply.sea_tracking import update_events
            changed = {}
            for mmsi, observed in inserted_rows:
                changed[mmsi] = min(observed, changed.get(mmsi, observed))
            update_events(conn, changed)
            data_store.bump_revision("sea", conn)
        return inserted


def import_csv(data: bytes) -> int:
    """Validate the entire upload before writing; reject malformed rows atomically."""
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("CSV没有船位报告")
    return archive_reports(rows)


def day_reports(day: date) -> list[dict]:
    start = datetime.combine(day, time.min, timezone.utc)
    end = start + timedelta(days=1)
    with connect_archive() as conn:
        rows = conn.execute("SELECT payload FROM ais_reports WHERE observed >= ? AND observed < ? "
                            "ORDER BY observed", (start.isoformat(), end.isoformat())).fetchall()
    return [json.loads(row[0]) for row in rows]


def day_snapshot(day: date) -> list[dict]:
    """Last observed report per vessel inside one UTC day, without date fallback."""
    start = datetime.combine(day, time.min, timezone.utc)
    end = start + timedelta(days=1)
    with connect_archive() as conn:
        rows = conn.execute(
            """SELECT payload FROM (
                   SELECT payload, observed,
                          ROW_NUMBER() OVER (
                              PARTITION BY mmsi
                              ORDER BY observed DESC,
                                       TRY_CAST(json_extract_string(payload,'$.received_at') AS TIMESTAMPTZ) DESC NULLS LAST,
                                       source ASC
                          ) AS source_rank
                   FROM ais_reports WHERE observed >= ? AND observed < ?
               ) ranked WHERE source_rank=1 ORDER BY observed DESC""",
            (start, end),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def snapshot_tracks(vessels: list[dict]) -> dict[str, list]:
    """Compact, time-ordered observed points, ending at each displayed marker."""
    selected = {str(v["mmsi"]): v for v in vessels if ais.parse_utc(v.get("observed_at"))}
    if not selected:
        return {}
    with connect_archive() as conn:
        rows = conn.execute("""
            WITH selected AS (
                SELECT UNNEST(?::VARCHAR[]) mmsi, UNNEST(?::TIMESTAMPTZ[]) cutoff
            ), ranked AS (
                SELECT a.mmsi, a.observed,
                       TRY_CAST(json_extract_string(a.payload,'$.lat') AS DOUBLE) lat,
                       TRY_CAST(json_extract_string(a.payload,'$.lon') AS DOUBLE) lon,
                       ROW_NUMBER() OVER (PARTITION BY a.mmsi,a.observed ORDER BY
                           TRY_CAST(json_extract_string(a.payload,'$.received_at') AS TIMESTAMPTZ) DESC NULLS LAST,
                           a.source ASC) source_rank
                FROM ais_reports a JOIN selected s ON a.mmsi=s.mmsi WHERE a.observed<=s.cutoff
            ) SELECT mmsi,observed,lat,lon FROM ranked WHERE source_rank=1
                AND lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180
            ORDER BY mmsi,observed
        """, [list(selected), [v["observed_at"] for v in selected.values()]]).fetchall()
    tracks = {mmsi: [] for mmsi in selected}
    for mmsi, observed, lat, lon in rows:
        tracks[mmsi].append([lat, lon, observed.isoformat()])
    for mmsi, vessel in selected.items():
        end = [vessel["lat"], vessel["lon"], ais.parse_utc(vessel["observed_at"]).isoformat()]
        if tracks[mmsi] and tracks[mmsi][-1][2] == end[2]:
            tracks[mmsi][-1] = end
        else:
            tracks[mmsi].append(end)
    return tracks


def latest_snapshot(max_age_minutes: int = 120, *, fallback_to_latest: bool = False) -> list[dict]:
    """Read recent positions, optionally retaining the last available local window."""
    window = timedelta(minutes=max(0, max_age_minutes))
    cutoff = ais.utc_now() - window
    with connect_archive() as conn:
        if fallback_to_latest:
            newest = conn.execute("SELECT MAX(observed) FROM ais_reports").fetchone()[0]
            if newest is not None and newest < cutoff:
                cutoff = newest - window
        rows = conn.execute(
            """SELECT payload FROM (
                   SELECT payload, observed,
                          ROW_NUMBER() OVER (
                              PARTITION BY mmsi
                              ORDER BY observed DESC,
                                       TRY_CAST(json_extract_string(payload,'$.received_at') AS TIMESTAMPTZ) DESC NULLS LAST,
                                       source ASC
                          ) AS source_rank
                   FROM ais_reports WHERE observed >= ?
               ) ranked
               WHERE source_rank=1
               ORDER BY observed DESC""",
            (cutoff.isoformat(),),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def known_mmsis() -> list[str]:
    with connect_archive() as conn:
        return [row[0] for row in conn.execute("SELECT mmsi FROM ais_reports GROUP BY mmsi "
                                              "ORDER BY MAX(observed) DESC LIMIT 1000").fetchall()]


def track_reports(feature: dict, expected_mmsi: str, day: date) -> list[dict]:
    """Normalize aligned track arrays; use only fields contained in the track."""
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    if feature.get("type") != "Feature" or feature.get("error"):
        raise ValueError("无法识别的历史轨迹响应")
    if geometry.get("type") == "LineString":
        coordinates = geometry.get("coordinates") or []
    elif geometry.get("type") == "Point":
        coordinates = [geometry["coordinates"]]
    elif not geometry:
        return []
    else:
        raise ValueError("不支持的轨迹几何")
    times = properties.get("times") or []
    if len(coordinates) != len(times):
        raise ValueError("轨迹坐标与时间未对齐")
    mmsi = str(properties.get("mmsi", feature.get("id", expected_mmsi)))
    if mmsi != expected_mmsi:
        raise ValueError("轨迹MMSI与请求不一致")
    credit = feature.get("attribution") or properties.get("attribution") or {}
    attribution = " · ".join(map(str, credit.values())) if isinstance(credit, dict) else str(credit)
    rows = []
    for index, coordinate in enumerate(coordinates):
        observed = ais.parse_utc(times[index])
        if observed is None or observed.date() != day:
            continue
        def value(key):
            values = properties.get(key) or []
            return values[index] if isinstance(values, list) and index < len(values) else None
        category, label = ais.classify_ship_type(ais.parse_integer(properties.get("type")))
        heading = ais.parse_number(value("heading"))
        course = heading if heading is not None and 0 <= heading < 360 else value("cog")
        try:
            rows.append(normalize_report({
                "mmsi": mmsi, "observed_at": times[index], "lon": coordinate[0],
                "received_at": ais.utc_now().isoformat(),
                "lat": coordinate[1], "name": properties.get("name"),
                "sog": value("sog"), "course": course, "category": category,
                "category_label": label,
                "navigation_status": ais.NAVIGATION_STATUS_LABELS.get(value("nav_status"), "未报告"),
                "source": "Open Waters track", "data_source": "Open Waters 历史轨迹",
                "source_url": ais.OPENWATERS_SOURCE, "source_attribution": attribution,
            }))
        except ValueError:
            # Vessel may have been outside these monitored waters that day.
            continue
    return rows


def _fetch_track(mmsi: str, day: date) -> tuple[list[dict], bool]:
    start = datetime.combine(day, time.min, timezone.utc)
    end = min(start + timedelta(days=1), ais.utc_now())
    params = urlencode({"from": start.isoformat(), "to": end.isoformat(), "limit": 1000})
    req = Request(f"{ais.OPENWATERS_API}/{mmsi}/track?{params}",
                  headers={"Accept": "application/geo+json", "User-Agent": "oil-field-map-demo/1.0"})
    with urlopen(req, timeout=8) as response:
        feature = json.load(response)
    return track_reports(feature, mmsi, day), bool(
        feature.get("truncated") or (feature.get("properties") or {}).get("truncated"))
