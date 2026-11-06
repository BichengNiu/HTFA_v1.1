"""Source normalization and bounded vessel snapshot preparation."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import htfa.monitoring.energy_supply.data.storage as data_store
from htfa.monitoring.energy_supply.data.openwaters_client import (
    fetch_group as _fetch_openwaters_group,
)
from htfa.monitoring.energy_supply.processing.regions import (
    AIS_COLLECTION_REGIONS,
    AIS_REGIONS,
)
from htfa.monitoring.energy_supply.processing.regions import (
    region_for as geographic_region_for,
)

SOURCE = "https://aisstream.io/documentation"
STREAM_URL = "wss://stream.aisstream.io/v0/stream"
OPENWATERS_SOURCE = "https://openwaters.io/ais/"
OPENWATERS_API = "https://ais.openwaters.io/v1/vessels"
MODULE_VERSION = 9
POSITION_RETENTION_SECONDS = 2 * 60 * 60
MAX_TRACKED_VESSELS = 20_000
MAX_ARCHIVE_BUFFER = 2_000
ARCHIVE_BATCH_SIZE = 50

# south, north, west, east. AIS covers the Red Sea corridor as well as PortWatch's waters.
REGIONS = AIS_REGIONS

# Open Waters' anonymous API allows 100 square degrees per request. Keep the
# complete corridor coverage in four requests while respecting that limit.
OPENWATERS_REGION_GROUPS = (
    ("波斯湾", "苏伊士运河"),
    ("阿曼湾", "亚丁湾", "曼德海峡"),
    ("红海北段", "红海北部两湾"),
    ("红海南段",),
)

POSITION_MESSAGE_TYPES = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "LongRangeAisBroadcastMessage",
)
STATIC_MESSAGE_TYPES = ("ShipStaticData", "StaticDataReport")
FILTER_MESSAGE_TYPES = (*POSITION_MESSAGE_TYPES, *STATIC_MESSAGE_TYPES)

VESSEL_TYPE_LABELS = {
    "tanker": "油轮/液货船",
    "cargo": "货船",
    "passenger": "客船",
    "fishing": "渔船",
    "tug": "拖轮/作业船",
    "pleasure": "帆船/游艇",
    "other": "其他船舶",
    "unknown": "船型待识别",
}

NAVIGATION_STATUS_LABELS = {
    0: "机动航行",
    1: "锚泊",
    2: "失控",
    3: "操纵能力受限",
    4: "受吃水限制",
    5: "系泊",
    6: "搁浅",
    7: "从事捕鱼",
    8: "帆船航行",
    14: "AIS-SART活动",
    15: "未定义",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def region_for(lat: float, lon: float) -> str | None:
    """Assign an AIS position to the monitored waters or the Red Sea corridor."""
    return geographic_region_for(lat, lon, REGIONS)


def in_collection_area(lat, lon):
    return geographic_region_for(lat, lon, AIS_COLLECTION_REGIONS) is not None


def openwaters_bbox_groups() -> tuple[tuple[tuple[float, float, float, float], ...], ...]:
    """Return south/north/west/east boxes grouped below Open Waters' free cap."""

    return tuple(
        tuple(AIS_COLLECTION_REGIONS[name] for name in group)
        for group in OPENWATERS_REGION_GROUPS
    )


@lru_cache(maxsize=1)
def _flag_names(snapshot_identity):
    return data_store.read_json("data/vessel_flag_names.json")["countries"]


def source_flag(value):
    """Retain source flag ISO codes; never infer registration from position."""
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code) or code in {"ZZ", "XX"}:
        return None, None
    return code, _flag_names(data_store.database_identity()).get(code, code)


def parse_utc(value: Any) -> datetime | None:
    """Normalize source timestamps to UTC, retaining missing or invalid values."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def openwaters_feature_to_vessel(
    feature: dict[str, Any], attribution: dict[str, Any] | None = None,
    received_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Normalize an Open Waters GeoJSON vessel feature for the map."""

    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if properties.get("kind", "vessel") != "vessel" or len(coordinates) < 2:
        return None
    lon = parse_number(coordinates[0])
    lat = parse_number(coordinates[1])
    if not valid_coordinate(lat, lon):
        return None
    assert lat is not None and lon is not None
    region = region_for(lat, lon)
    if not in_collection_area(lat, lon):
        return None

    mmsi = parse_integer(properties.get("mmsi", feature.get("id")))
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        return None
    observed = parse_utc(properties.get("seen"))
    received = received_at or utc_now()
    sog = parse_number(properties.get("sog"))
    cog = parse_number(properties.get("cog"))
    heading = parse_number(properties.get("heading"))
    if sog is not None and not 0 <= sog < 102.3:
        sog = None
    if cog is not None and not 0 <= cog < 360:
        cog = None
    if heading is not None and not 0 <= heading < 360:
        heading = None
    ship_type = parse_integer(properties.get("type"))
    category, category_label = classify_ship_type(ship_type)
    nav_code = parse_integer(properties.get("nav_status"))
    source = _clean_text(properties.get("source")) or "Open Waters"
    station = _clean_text(properties.get("station"))
    attribution_text = (attribution or {}).get(source)
    source_url_match = re.search(r"https?://[^\s)]+", str(attribution_text or ""))
    source_url = source_url_match.group(0).rstrip(".,") if source_url_match else OPENWATERS_SOURCE
    flag, flag_country = source_flag(properties.get("flag"))
    age_minutes = (max(0.0, (utc_now() - observed).total_seconds() / 60)
                   if observed else None)
    return {
        "mmsi": str(mmsi),
        "flag": flag,
        "flag_country": flag_country,
        "flag_source": OPENWATERS_API if flag else None,
        "observed_at": observed.isoformat() if observed else None,
        "received_at": received.isoformat(),
        "message_type": _clean_text(properties.get("msg_type")) or "PositionReport",
        "kind": "position",
        "name": _clean_text(properties.get("name")),
        "lat": lat,
        "lon": lon,
        "region": region,
        "sog": sog,
        "cog": cog,
        "heading": heading,
        "course": heading if heading is not None else cog,
        "navigation_status_code": nav_code,
        "navigation_status": NAVIGATION_STATUS_LABELS.get(nav_code, "未报告"),
        "ship_type_code": ship_type,
        "category": category if ship_type is not None else "unknown",
        "category_label": category_label if ship_type is not None else VESSEL_TYPE_LABELS["unknown"],
        "imo": parse_integer(properties.get("imo")),
        "call_sign": _clean_text(properties.get("callsign", properties.get("call_sign"))),
        "destination": _clean_text(properties.get("dest", properties.get("destination"))),
        "draught": parse_number(properties.get("draught")),
        "moving": (sog or 0) >= 0.5,
        "age_minutes": age_minutes,
        "age_basis": "源站观测时间" if observed else None,
        "data_source": f"Open Waters · {source}",
        "source": source,
        "station": station,
        "source_url": source_url,
        "source_attribution": _clean_text(attribution_text),
    }




def openwaters_snapshot(max_age_minutes: int = 30) -> dict[str, Any]:
    """Fetch a free Open Waters snapshot for all monitored areas."""

    groups = openwaters_bbox_groups()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        futures = [pool.submit(copy_context().run, _fetch_openwaters_group, group, max_age_minutes)
                   for group in groups]
    for future in as_completed(futures):
        try:
            results.append(future.result())
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

    received_at = utc_now()
    attribution: dict[str, str] = {}
    by_mmsi: dict[str, dict[str, Any]] = {}
    reports = []
    truncated = False
    for result in results:
        source_attribution = result.get("attribution") or {}
        if isinstance(source_attribution, dict):
            attribution.update({str(key): str(value)
                                for key, value in source_attribution.items()})
        truncated = truncated or bool(result.get("truncated"))
        for feature in result.get("features") or []:
            if not isinstance(feature, dict):
                continue
            vessel = openwaters_feature_to_vessel(feature, attribution, received_at)
            if vessel is None:
                continue
            reports.append(vessel)
            previous = by_mmsi.get(vessel["mmsi"])
            if previous is None or _snapshot_is_newer(vessel, previous):
                by_mmsi[vessel["mmsi"]] = vessel

    # Resolve attribution after combining all area responses.
    for vessel in by_mmsi.values():
        vessel["source_attribution"] = attribution.get(vessel["source"])
    return {
        "vessels": sorted(
            by_mmsi.values(), key=_snapshot_timestamp, reverse=True),
        "attribution": attribution,
        "truncated": truncated,
        "fetched_at": received_at.isoformat(),
        "error": "; ".join(errors) if errors else None,
        "reports": reports,
        "requested_groups": len(groups),
        "successful_groups": len(results),
    }


def subscription(api_key: str) -> dict[str, Any]:
    """Build the complete AISStream subscription sent immediately after connect."""

    return {
        "APIKey": api_key,
        "BoundingBoxes": [
            [[north, west], [south, east]]
            for south, north, west, east in AIS_COLLECTION_REGIONS.values()
        ],
        "FilterMessageTypes": list(FILTER_MESSAGE_TYPES),
    }


def classify_ship_type(ship_type: int | None) -> tuple[str, str]:
    """Map the base AIS ship-type code to a deliberately broad category."""

    if ship_type is None:
        category = "unknown"
    elif 80 <= ship_type <= 89:
        category = "tanker"
    elif 70 <= ship_type <= 79:
        category = "cargo"
    elif 60 <= ship_type <= 69:
        category = "passenger"
    elif ship_type == 30:
        category = "fishing"
    elif ship_type in {31, 32, 50, 51, 52, 53, 54, 55, 58}:
        category = "tug"
    elif ship_type in {36, 37}:
        category = "pleasure"
    elif 1 <= ship_type <= 99:
        category = "other"
    else:
        category = "unknown"
    return category, VESSEL_TYPE_LABELS[category]


def merge_vessel_snapshots(
    *snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge snapshots by MMSI, preserving the newest report for each vessel."""

    by_mmsi: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        for vessel in snapshot:
            mmsi = str(vessel["mmsi"])
            previous = by_mmsi.get(mmsi)
            if previous is None or _snapshot_is_newer(vessel, previous):
                by_mmsi[mmsi] = vessel
    return list(by_mmsi.values())


def _snapshot_is_newer(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    """Compare observations when both exist, otherwise compare local receipts."""
    candidate_observed = parse_utc(candidate.get("observed_at"))
    current_observed = parse_utc(current.get("observed_at"))
    if candidate_observed and current_observed:
        return candidate_observed >= current_observed
    candidate_received = parse_utc(candidate.get("received_at"))
    current_received = parse_utc(current.get("received_at"))
    return candidate_received is not None and (
        current_received is None or candidate_received >= current_received)


def _snapshot_timestamp(vessel: dict[str, Any]) -> float:
    """Return the best available UTC timestamp for ordering map snapshots."""
    observed = parse_utc(vessel.get("observed_at"))
    received = parse_utc(vessel.get("received_at"))
    timestamp = observed or received
    return timestamp.timestamp() if timestamp else float("-inf")


def parse_number(value: Any) -> float | None:
    """Parse a numeric AIS field without inventing a value on failure."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def parse_integer(value: Any) -> int | None:
    """Parse an integral identifier or AIS category code."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("@", "").strip()
    return text or None


def valid_coordinate(lat: float | None, lon: float | None) -> bool:
    """Validate a latitude/longitude pair before region classification."""
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def normalize_event(event: dict[str, Any], received_at: datetime | None = None) -> dict[str, Any] | None:
    """Normalize one AISStream event into a position or static-data update."""

    message_type = event.get("MessageType")
    if message_type not in FILTER_MESSAGE_TYPES:
        return None
    metadata = event.get("MetaData") or {}
    message = event.get("Message") or {}
    payload = message.get(message_type) or {}
    mmsi_value = metadata.get("MMSI", payload.get("UserID"))
    mmsi_int = parse_integer(mmsi_value)
    if mmsi_int is None or not 100000000 <= mmsi_int <= 999999999:
        return None
    received = received_at or utc_now()
    observed = parse_utc(
        metadata.get("time_utc", metadata.get("TimeUTC", metadata.get("timestamp"))))
    base: dict[str, Any] = {
        "mmsi": str(mmsi_int),
        "observed_at": observed.isoformat() if observed else None,
        "received_at": received.isoformat(),
        "message_type": message_type,
    }

    if message_type in POSITION_MESSAGE_TYPES:
        lat = parse_number(metadata.get("Latitude", payload.get("Latitude")))
        lon = parse_number(metadata.get("Longitude", payload.get("Longitude")))
        if not valid_coordinate(lat, lon):
            return None
        assert lat is not None and lon is not None
        sog = parse_number(payload.get("Sog"))
        cog = parse_number(payload.get("Cog"))
        heading = parse_number(payload.get("TrueHeading"))
        # AIS sentinels: SOG 102.3, COG 3600/360, heading 511.
        if sog is not None and not 0 <= sog < 102.3:
            sog = None
        if cog is not None and not 0 <= cog < 360:
            cog = None
        if heading is not None and not 0 <= heading < 360:
            heading = None
        nav_code = parse_integer(payload.get("NavigationalStatus"))
        base.update({
            "kind": "position",
            "name": _clean_text(metadata.get("ShipName")),
            "lat": lat,
            "lon": lon,
            "region": region_for(lat, lon),
            "sog": sog,
            "cog": cog,
            "heading": heading,
            "course": heading if heading is not None else cog,
            "navigation_status_code": nav_code,
            "navigation_status": NAVIGATION_STATUS_LABELS.get(nav_code, "未报告"),
        })
        # Extended Class B reports can carry the base ship-type code directly.
        ship_type = parse_integer(payload.get("Type", payload.get("ShipType")))
        if ship_type is not None:
            category, label = classify_ship_type(ship_type)
            base.update({"ship_type_code": ship_type, "category": category,
                         "category_label": label})
        return base

    # Message 24 (Class B static data) arrives as independent ReportA/name and
    # ReportB/type + call-sign parts.  Keep absent fields as None so one part
    # cannot overwrite useful data already received from the other part.
    report_a = payload.get("ReportA") or {}
    report_b = payload.get("ReportB") or {}
    if not report_a.get("Valid", True):
        report_a = {}
    if not report_b.get("Valid", True):
        report_b = {}
    ship_type = parse_integer(payload.get(
        "Type", payload.get("ShipType", report_b.get("ShipType"))))
    category, label = classify_ship_type(ship_type)
    base.update({
        "kind": "static",
        "name": _clean_text(
            payload.get("Name", payload.get(
                "ShipName", report_a.get("Name", metadata.get("ShipName"))))),
        "call_sign": _clean_text(payload.get("CallSign", report_b.get("CallSign"))),
        "imo": parse_integer(payload.get("ImoNumber", payload.get("IMO"))),
        "destination": _clean_text(
            payload.get("DestinationName", payload.get("Destination"))),
        "draught": parse_number(payload.get("MaximumStaticDraught", payload.get("Draught"))),
        "ship_type_code": ship_type,
        "category": category if ship_type is not None else None,
        "category_label": label if ship_type is not None else None,
    })
    return base


def _normalization_rejection_reason(event: dict[str, Any]) -> str:
    """Return a safe, compact reason for a decoded event that was not accepted."""

    message_type = event.get("MessageType")
    if message_type not in FILTER_MESSAGE_TYPES:
        return f"不支持的消息类型：{message_type or '缺失'}"
    metadata = event.get("MetaData")
    metadata = metadata if isinstance(metadata, dict) else {}
    message = event.get("Message")
    message = message if isinstance(message, dict) else {}
    payload = message.get(message_type)
    payload = payload if isinstance(payload, dict) else {}
    mmsi_value = metadata.get("MMSI", payload.get("UserID"))
    mmsi = parse_integer(mmsi_value)
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        return "MMSI缺失或无效"
    if message_type in POSITION_MESSAGE_TYPES:
        lat = parse_number(metadata.get("Latitude", payload.get("Latitude")))
        lon = parse_number(metadata.get("Longitude", payload.get("Longitude")))
        if not valid_coordinate(lat, lon):
            return "经纬度缺失或无效"
    return "消息结构不符合预期"
