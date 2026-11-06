from htfa.monitoring.energy_supply.data import queries

"""Read-only AIS history: count observed vessels, never position messages."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

import htfa.monitoring.energy_supply.processing.ais as ais
from htfa.monitoring.energy_supply.processing.vessel_display import destination_label

CHART_REGIONS = ("霍尔木兹海峡", "阿曼湾", "波斯湾")
CHART_TYPES = {"tanker": "油轮/液货船", "cargo": "货船", "other_unknown": "其他/未知船型"}
CHART_LABELS = {**{r: f"{r}观测去重船数" for r in CHART_REGIONS},
                **{key: f"{label}观测去重船数" for key, label in CHART_TYPES.items()}}
CHART_FIELDS = ("date", "period_start", "period_end", *CHART_LABELS)


def flag_label(row):
    return row.get("flag_country") or row.get("flag") or "未知船籍"


def matches(row, flags, destinations):
    return flag_label(row) in flags and destination_label(row) in destinations


def metrics(vessels, available):
    def count(predicate):
        return sum(predicate(row) for row in vessels) if available else "—"
    return [
        ("航行中", count(lambda r: r.get("sog") is not None and r["sog"] >= .5)),
        ("停泊中", count(lambda r: r.get("sog") is not None and r["sog"] < .5)),
        ("油轮/液货船", count(lambda r: r.get("category") == "tanker")),
        ("货船", count(lambda r: r.get("category") == "cargo")),
        ("其他/未知船型", count(lambda r: r.get("category") not in ("tanker", "cargo"))),
        ("中国籍船", count(lambda r: r.get("flag") == "CN")),
    ]


def history(last: date, snapshot_identity: tuple) -> list[dict]:
    return queries.vessel_history(last)


def bucket(day, aggregation):
    if aggregation == "周度":
        return day-timedelta(days=day.weekday())
    if aggregation == "月度":
        return day.replace(day=1)
    if aggregation == "年度":
        return day.replace(month=1, day=1)
    if aggregation != "日度":
        raise ValueError("未知聚合方式")
    return day


def aggregate(rows, first, last, aggregation, flags, destinations):
    observed = defaultdict(set)
    vessels = defaultdict(set)
    latest = {}
    for row in rows:
        timestamp = ais.parse_utc(row.get("observed_at"))
        if timestamp is None or not first <= timestamp.date() <= last:
            continue
        region = row.get("region")
        start = bucket(timestamp.date(), aggregation)
        observed[start].add(region)
        if matches(row, flags, destinations) and row.get("mmsi"):
            vessels[start, region].add(str(row["mmsi"]))
            # A ship moving between waters is still one ship in the type charts.
            key = (start, str(row["mmsi"]))
            if key not in latest or timestamp >= latest[key][0]:
                latest[key] = (timestamp, row.get("category"))
    types = defaultdict(set)
    for (start, mmsi), (_, category) in latest.items():
        kind = category if category in ("tanker", "cargo") else "other_unknown"
        types[start, kind].add(mmsi)
    result = []
    cursor = bucket(first, aggregation)
    while cursor <= last:
        end = (cursor+timedelta(days=6) if aggregation == "周度" else
               cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1]) if aggregation == "月度" else
               cursor.replace(month=12, day=31) if aggregation == "年度" else cursor)
        record = {"date": cursor, "period_start": max(first, cursor), "period_end": min(last, end)}
        for region in ais.REGIONS:
            record[region] = len(vessels[cursor, region]) if region in observed[cursor] else None
        for kind in CHART_TYPES:
            record[kind] = len(types[cursor, kind]) if observed[cursor] else None
        result.append(record)
        cursor = end+timedelta(days=1)
    return result


def series_labels():
    suffix = "末次采样存量"
    return {**{r: f"{r}{suffix}" for r in CHART_REGIONS},
            **{key: f"{label}{suffix}" for key, label in CHART_TYPES.items()}}


def stock_series(rows, first, last, aggregation, flags, destinations):
    """Last sampled day per period; one common cutoff and <=120 minute age.

    A sample is receiver-visible stock, not a census of all vessels present.
    Select latest positions before filtering metadata or assigning waters.
    """
    by_day = defaultdict(list)
    for row in rows:
        timestamp = ais.parse_utc(row.get("observed_at"))
        if timestamp and first <= timestamp.date() <= last:
            by_day[timestamp.date()].append((timestamp, row))
    records = {r["date"]: r for r in aggregate([], first, last, aggregation, flags, destinations)}
    for day, reports in sorted(by_day.items()):
        anchor = max(timestamp for timestamp, _ in reports)
        fresh = {}
        for timestamp, row in sorted(reports, key=lambda item: item[0]):
            if timestamp >= anchor-timedelta(minutes=120) and row.get("mmsi"):
                fresh[str(row["mmsi"])] = row
        # Later sampled days replace earlier samples, never sum inventories.
        record = records[bucket(day, aggregation)]
        record["sample_at"] = anchor.isoformat()
        covered = {r.get("region") for r in fresh.values()}
        selected = [r for r in fresh.values() if matches(r, flags, destinations)]
        for region in ais.REGIONS:
            record[region] = sum(r.get("region") == region for r in selected) if region in covered else None
        for kind in CHART_TYPES:
            record[kind] = sum((r.get("category") if r.get("category") in ("tanker", "cargo")
                                else "other_unknown") == kind for r in selected)
    return list(records.values())
