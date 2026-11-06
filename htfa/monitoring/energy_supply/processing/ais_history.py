"""Observed AIS reports only: persistent archive and bounded recent backfill."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import htfa.monitoring.energy_supply.data.storage as data_store
import htfa.monitoring.energy_supply.processing.ais as ais
from htfa.monitoring.energy_supply.data import ais_repository as repository
from htfa.monitoring.energy_supply.data.openwaters_client import fetch_track


def archive_path() -> Path:
    return data_store.database_path()


def normalize_report(row: dict) -> dict:
    """Keep source observation time distinct from collector receipt time."""
    mmsi = ais.parse_integer(row.get("mmsi", row.get("MMSI")))
    observed = ais.parse_utc(row.get("observed_at", row.get("AIS报告时间 UTC")))
    # Preserve explicit historical imports; current live rows include a source
    # label and therefore must provide an observed_at value.
    if observed is None and not row.get("data_source"):
        observed = ais.parse_utc(row.get("received_at"))
    received = (
        ais.parse_utc(row.get("received_at", row.get("采集器接收时间 UTC")))
        or ais.utc_now()
    )
    lat = ais.parse_number(row.get("lat", row.get("纬度")))
    lon = ais.parse_number(row.get("lon", row.get("经度")))
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        raise ValueError("MMSI无效")
    if observed is None or observed > ais.utc_now() + timedelta(minutes=5):
        raise ValueError("AIS报告时间缺失、无效或在未来")
    if not ais.valid_coordinate(lat, lon) or not ais.in_collection_area(lat, lon):
        raise ValueError("坐标无效或不在监测水域及边界观测带")
    category = row.get("category") or next(
        (
            key
            for key, label in ais.VESSEL_TYPE_LABELS.items()
            if label == row.get("船型")
        ),
        "unknown",
    )
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
    return {
        **row,
        "mmsi": str(mmsi),
        "observed_at": observed.isoformat(),
        "received_at": received.isoformat(),
        "provider_received_at": row.get(
            "provider_received_at", row.get("采集器接收时间 UTC")
        ),
        "lat": lat,
        "lon": lon,
        "region": ais.region_for(lat, lon),
        "name": row.get("name", row.get("船名")),
        "imo": row.get("imo", row.get("IMO")),
        "sog": sog,
        "course": course,
        "moving": (sog or 0) >= 0.5,
        "category": category,
        "category_label": ais.VESSEL_TYPE_LABELS[category],
        "navigation_status": row.get("navigation_status", row.get("航行状态")),
        "destination": row.get("destination", row.get("目的地")),
        "draught": row.get("draught", row.get("吃水 米")),
        "source": str(source),
        "data_source": row.get("data_source", str(source)),
        "source_url": row.get("source_url", row.get("来源")),
        "age_minutes": None,
    }


def archive_reports(rows: list[dict]) -> int:
    """Validate reports and derive sea events in the same atomic archive write."""
    normalized = [
        normalize_report(row)
        for row in rows
        if row.get("observed_at")
        or row.get("AIS报告时间 UTC")
        or not row.get("data_source")
    ]
    if not normalized:
        return 0
    with repository.transaction() as transaction:
        inserted_rows, updated = repository.save_reports(normalized, transaction)
        if inserted_rows or updated:
            data_store.bump_revision("ais", transaction)
        if inserted_rows:
            from htfa.monitoring.energy_supply.processing.sea_tracking import (
                update_events,
            )

            changed = {}
            for mmsi, observed in inserted_rows:
                changed[mmsi] = min(observed, changed.get(mmsi, observed))
            update_events(transaction, changed)
            data_store.bump_revision("sea", transaction)
        return len(inserted_rows)


def import_csv(data: bytes) -> int:
    """Validate the entire upload before writing; reject malformed rows atomically."""
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("CSV没有船位报告")
    return archive_reports(rows)


def day_reports(day: date) -> list[dict]:
    start = datetime.combine(day, time.min, timezone.utc)
    return repository.reports_between(start, start + timedelta(days=1))


def day_snapshot(day: date) -> list[dict]:
    """Select the last observed report per vessel inside the selected UTC day."""
    start = datetime.combine(day, time.min, timezone.utc)
    return repository.reports_between(
        start, start + timedelta(days=1), latest_per_vessel=True
    )


def snapshot_tracks(vessels: list[dict]) -> dict[str, list]:
    """Compact, time-ordered observed points, ending at each displayed marker."""
    selected = {
        str(v["mmsi"]): v for v in vessels if ais.parse_utc(v.get("observed_at"))
    }
    if not selected:
        return {}
    rows = repository.track_points(selected)
    tracks = {mmsi: [] for mmsi in selected}
    for mmsi, observed, lat, lon in rows:
        tracks[mmsi].append([lat, lon, observed.isoformat()])
    for mmsi, vessel in selected.items():
        end = [
            vessel["lat"],
            vessel["lon"],
            ais.parse_utc(vessel["observed_at"]).isoformat(),
        ]
        if tracks[mmsi] and tracks[mmsi][-1][2] == end[2]:
            tracks[mmsi][-1] = end
        else:
            tracks[mmsi].append(end)
    return tracks


def latest_snapshot(
    max_age_minutes: int = 120, *, fallback_to_latest: bool = False
) -> list[dict]:
    """Select the recent window, optionally anchored to the last published observation."""
    window = timedelta(minutes=max(0, max_age_minutes))
    cutoff = ais.utc_now() - window
    if fallback_to_latest:
        newest = repository.latest_observed()
        if newest is not None and newest < cutoff:
            cutoff = newest - window
    return repository.positions_since(cutoff)


def known_mmsis() -> list[str]:
    return repository.known_mmsis()


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
    attribution = (
        " · ".join(map(str, credit.values()))
        if isinstance(credit, dict)
        else str(credit)
    )
    rows = []
    for index, coordinate in enumerate(coordinates):
        observed = ais.parse_utc(times[index])
        if observed is None or observed.date() != day:
            continue

        def value(key):
            values = properties.get(key) or []
            return (
                values[index]
                if isinstance(values, list) and index < len(values)
                else None
            )

        category, label = ais.classify_ship_type(
            ais.parse_integer(properties.get("type"))
        )
        heading = ais.parse_number(value("heading"))
        course = heading if heading is not None and 0 <= heading < 360 else value("cog")
        try:
            rows.append(
                normalize_report(
                    {
                        "mmsi": mmsi,
                        "observed_at": times[index],
                        "lon": coordinate[0],
                        "received_at": ais.utc_now().isoformat(),
                        "lat": coordinate[1],
                        "name": properties.get("name"),
                        "sog": value("sog"),
                        "course": course,
                        "category": category,
                        "category_label": label,
                        "navigation_status": ais.NAVIGATION_STATUS_LABELS.get(
                            value("nav_status"), "未报告"
                        ),
                        "source": "Open Waters track",
                        "data_source": "Open Waters 历史轨迹",
                        "source_url": ais.OPENWATERS_SOURCE,
                        "source_attribution": attribution,
                    }
                )
            )
        except ValueError:
            # Vessel may have been outside these monitored waters that day.
            continue
    return rows


def _fetch_track(mmsi: str, day: date) -> tuple[list[dict], bool]:
    start = datetime.combine(day, time.min, timezone.utc)
    end = min(start + timedelta(days=1), ais.utc_now())
    feature = fetch_track(mmsi, start, end)
    return track_reports(feature, mmsi, day), bool(
        feature.get("truncated") or (feature.get("properties") or {}).get("truncated")
    )
