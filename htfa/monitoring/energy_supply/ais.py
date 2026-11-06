"""Server-side AISStream collector and normalized vessel snapshots.

The collector intentionally keeps the API key and raw WebSocket connection on the
server.  The Streamlit/Leaflet client only receives a bounded latest-position
snapshot with no credentials.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from htfa.monitoring.energy_supply.regions import AIS_REGIONS, AIS_COLLECTION_REGIONS, region_for as geographic_region_for
from htfa.monitoring.energy_supply import data_store

try:
    from websockets.sync.client import connect as websocket_connect
except ImportError:  # The rest of the application must still work without AIS.
    websocket_connect = None


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
def _flag_names():
    return data_store.read_json("data/vessel_flag_names.json")["countries"]


def source_flag(value):
    """Retain source flag ISO codes; never infer registration from position."""
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code) or code in {"ZZ", "XX"}:
        return None, None
    return code, _flag_names().get(code, code)


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


def _fetch_openwaters_group(
    boxes: tuple[tuple[float, float, float, float], ...], max_age_minutes: int,
    *, split_depth: int = 0,
) -> dict[str, Any]:
    if data_store.read_only():
        raise RuntimeError("只读展示端不允许采集船位")
    params = [("bbox", f"{south},{west},{north},{east}")
              for south, north, west, east in boxes]
    params.append(("max_age", f"{max_age_minutes}m"))
    request = Request(
        f"{OPENWATERS_API}?{urlencode(params)}",
        headers={"User-Agent": "oil-field-map-demo/1.0", "Accept": "application/geo+json, application/json"},
    )
    with urlopen(request, timeout=8) as response:
        result = json.load(response)
    data_store.save_query(OPENWATERS_API, {"query_parameters": params}, result)
    if not isinstance(result, dict) or result.get("type") != "FeatureCollection":
        raise ValueError("Open Waters返回了无法识别的船位快照")
    if result.get("error"):
        raise ValueError(f"Open Waters API：{result['error']}")
    if result.get("truncated") and split_depth < 3:
        # Dense areas may hit the provider's response cap even below its area
        # limit. Retry smaller areas; never relabel the partial parent as full.
        if len(boxes) > 1:
            parts = [(box,) for box in boxes]
        else:
            south, north, west, east = boxes[0]
            if east - west >= north - south:
                middle = (west + east) / 2
                parts = [((south, north, west, middle),), ((south, north, middle, east),)]
            else:
                middle = (south + north) / 2
                parts = [((south, middle, west, east),), ((middle, north, west, east),)]
        children = [_fetch_openwaters_group(part, max_age_minutes, split_depth=split_depth + 1)
                    for part in parts]
        result = {
            "type": "FeatureCollection",
            "features": [feature for child in children for feature in child.get("features", [])],
            "attribution": {key: value for child in children for key, value in (child.get("attribution") or {}).items()},
            "truncated": any(bool(child.get("truncated")) for child in children),
        }
    return result


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


class AISCollector:
    """A reconnecting, thread-safe latest-position collector."""

    def __init__(self, api_key: str, connector: Callable[..., Any] | None = None) -> None:
        self._api_key = api_key
        self._connector = connector or websocket_connect
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._positions: dict[str, dict[str, Any]] = {}
        self._static: dict[str, dict[str, Any]] = {}
        self._status = "未启动"
        self._last_error: str | None = None
        self._last_message_at: str | None = None
        self._last_position_message_at: str | None = None
        self._last_raw_event_at: str | None = None
        self._last_raw_message_type: str | None = None
        self._last_rejection_reason: str | None = None
        self._message_count = 0
        self._raw_event_count = 0
        self._rejected_event_count = 0
        self._position_message_count = 0
        self._static_message_count = 0
        self._connected_at: str | None = None
        self._subscription_confirmed_at: str | None = None
        self._compression_enabled: bool | None = None
        self._archive_error: str | None = None
        self._archive_buffer: deque[dict[str, Any]] = deque()
        self._archive_dropped_count = 0
        self._archive_unobserved_count = 0
        self._archive_wakeup = threading.Event()
        self._archive_thread: threading.Thread | None = None
        self._socket: Any | None = None
        self._ingest_since_prune = 0

    def start(self) -> "AISCollector":
        if self._thread and self._thread.is_alive():
            return self
        if not self._api_key:
            with self._lock:
                self._status = "未配置密钥"
            return self
        if self._connector is None:
            with self._lock:
                self._status = "缺少 websockets 依赖"
                self._last_error = "请安装 requirements.txt 后重启应用"
            return self
        self._stop.clear()
        self._archive_wakeup.clear()
        self._archive_thread = threading.Thread(
            target=self._archive_worker, name="ais-archive-writer", daemon=True)
        self._archive_thread.start()
        self._thread = threading.Thread(
            target=self._run, name="aisstream-collector", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._archive_wakeup.set()
        with self._lock:
            socket = self._socket
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=7)
        if self._archive_thread and self._archive_thread.is_alive():
            self._archive_thread.join(timeout=3)

    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            connected_monotonic = None
            try:
                with self._lock:
                    self._status = "连接中" if attempt == 0 else "重连中"
                assert self._connector is not None
                with self._connector(
                    STREAM_URL, open_timeout=10, close_timeout=5,
                    ping_interval=20, ping_timeout=20, compression="deflate",
                    max_size=2 * 1024 * 1024,
                ) as socket:
                    connected_monotonic = time.monotonic()
                    with self._lock:
                        self._socket = socket
                    socket.send(json.dumps(subscription(self._api_key)))
                    with self._lock:
                        self._status = "已连接，等待订阅确认"
                        self._connected_at = utc_now().isoformat()
                        self._last_error = None
                    while not self._stop.is_set():
                        try:
                            frame = socket.recv(timeout=5)
                        except TimeoutError:
                            self._archive_wakeup.set()
                            continue
                        if isinstance(frame, bytes):
                            frame = frame.decode("utf-8")
                        event = json.loads(frame)
                        if event.get("MessageType") == "SubscriptionConfirmation":
                            confirmation = event.get("Message") or {}
                            compression_enabled = confirmation.get("CompressionEnabled")
                            if not isinstance(compression_enabled, bool):
                                compression_enabled = None
                            with self._lock:
                                self._status = "订阅已确认"
                                self._subscription_confirmed_at = utc_now().isoformat()
                                self._compression_enabled = compression_enabled
                            self._archive_wakeup.set()
                            continue
                        if event.get("error"):
                            raise RuntimeError(str(event["error"]))
                        self.ingest(event)
            except Exception as exc:  # Network failures are expected; reconnect safely.
                self._archive_wakeup.set()
                if (connected_monotonic is not None
                        and time.monotonic() - connected_monotonic >= 60):
                    attempt = 0
                attempt += 1
                with self._lock:
                    self._status = "重连等待"
                    self._last_error = f"{type(exc).__name__}: {exc}"
                delay = min(60.0, 2 ** min(attempt, 5)) + random.random()
                self._stop.wait(delay)
            finally:
                with self._lock:
                    self._socket = None
        with self._lock:
            self._status = "已停止"
        self._archive_wakeup.set()

    def _archive_worker(self) -> None:
        """Persist batches away from the websocket receive loop."""
        while True:
            self._archive_wakeup.wait(timeout=5)
            self._archive_wakeup.clear()
            with self._lock:
                batch = [self._archive_buffer.popleft() for _ in range(
                    min(ARCHIVE_BATCH_SIZE, len(self._archive_buffer)))]
                should_stop = self._stop.is_set() and not self._archive_buffer
            if batch:
                try:
                    from htfa.monitoring.energy_supply import ais_history
                    ais_history.archive_reports(batch)
                    with self._lock:
                        self._archive_error = None
                except Exception as exc:
                    with self._lock:
                        self._archive_error = f"{type(exc).__name__}: {exc}"
                        for report in reversed(batch):
                            self._archive_buffer.appendleft(report)
                        while len(self._archive_buffer) > MAX_ARCHIVE_BUFFER:
                            self._archive_buffer.pop()
                            self._archive_dropped_count += 1
                    if self._stop.is_set():
                        return
                    self._stop.wait(5)
            if should_stop:
                return

    def ingest(self, event: dict[str, Any], received_at: datetime | None = None) -> bool:
        received = received_at or utc_now()
        message_type = str(event.get("MessageType") or "缺失")
        with self._lock:
            self._raw_event_count += 1
            self._last_raw_event_at = received.isoformat()
            self._last_raw_message_type = message_type
        try:
            normalized = normalize_event(event, received)
        except Exception as exc:
            with self._lock:
                self._rejected_event_count += 1
                self._last_rejection_reason = f"解析异常：{type(exc).__name__}"
            return False
        if normalized is None:
            reason = _normalization_rejection_reason(event)
            with self._lock:
                self._rejected_event_count += 1
                self._last_rejection_reason = reason
            return False
        normalized["data_source"] = "AISStream"
        normalized["source"] = "AISStream"
        normalized["source_url"] = SOURCE
        normalized["source_attribution"] = "AISStream"
        mmsi = normalized["mmsi"]
        with self._lock:
            self._message_count += 1
            self._last_message_at = normalized["received_at"]
            if normalized["kind"] == "static":
                self._static_message_count += 1
                previous = self._static.get(mmsi, {})
                if not previous or _snapshot_is_newer(normalized, previous):
                    self._static[mmsi] = {
                        **previous,
                        **{key: value for key, value in normalized.items()
                           if value is not None},
                    }
            else:
                self._position_message_count += 1
                self._last_position_message_at = normalized["received_at"]
                previous = self._positions.get(mmsi, {})
                # Position reports replace dynamic values, including invalid AIS
                # sentinels normalized to None. Stale SOG/course must not survive.
                if not previous or _snapshot_is_newer(normalized, previous):
                    self._positions[mmsi] = normalized
            self._ingest_since_prune += 1
            if self._ingest_since_prune >= 256:
                received_utc = parse_utc(received.isoformat())
                self._prune_state_locked(received_utc.timestamp() if received_utc else 0)
                self._ingest_since_prune = 0
        if normalized["kind"] == "position" and in_collection_area(normalized["lat"], normalized["lon"]):
            with self._lock:
                if normalized.get("observed_at"):
                    static = self._static.get(mmsi, {})
                    archive_row = {**static, **{
                        key: value for key, value in normalized.items()
                        if value is not None}}
                    self._archive_buffer.append(archive_row)
                    if len(self._archive_buffer) > MAX_ARCHIVE_BUFFER:
                        self._archive_buffer.popleft()
                        self._archive_dropped_count += 1
                    if len(self._archive_buffer) >= ARCHIVE_BATCH_SIZE:
                        self._archive_wakeup.set()
                else:
                    self._archive_unobserved_count += 1
        return True

    def _prune_state_locked(self, now_timestamp: float) -> None:
        cutoff = now_timestamp - POSITION_RETENTION_SECONDS
        stale = []
        for mmsi, position in self._positions.items():
            received = parse_utc(position.get("received_at"))
            if received is None or received.timestamp() < cutoff:
                stale.append(mmsi)
        for mmsi in stale:
            self._positions.pop(mmsi, None)
            self._static.pop(mmsi, None)
        if len(self._positions) > MAX_TRACKED_VESSELS:
            oldest = sorted(self._positions, key=lambda key: self._positions[key]["received_at"])
            for mmsi in oldest[:len(self._positions) - MAX_TRACKED_VESSELS]:
                self._positions.pop(mmsi, None)
                self._static.pop(mmsi, None)
        if len(self._static) > MAX_TRACKED_VESSELS:
            oldest = sorted(self._static, key=lambda key: self._static[key].get("received_at", ""))
            for mmsi in oldest[:len(self._static) - MAX_TRACKED_VESSELS]:
                self._static.pop(mmsi, None)

    def snapshot(self, max_age_minutes: int = 30,
                 limit: int | None = None) -> list[dict[str, Any]]:
        now = utc_now()
        cutoff = now.timestamp() - max_age_minutes * 60
        with self._lock:
            rows = []
            for mmsi, position in self._positions.items():
                received = parse_utc(position.get("received_at"))
                if received is None:
                    continue
                static = self._static.get(mmsi, {})
                merged = {**position, **{
                    key: value for key, value in static.items()
                    if position.get(key) in (None, "")}}
                # Position messages often carry the fresher ship name; static data owns type.
                if static.get("category"):
                    merged["category"] = static["category"]
                    merged["category_label"] = static["category_label"]
                    merged["ship_type_code"] = static.get("ship_type_code")
                observation = parse_utc(merged.get("observed_at"))
                age_time = observation or received
                if age_time.timestamp() < cutoff:
                    continue
                category = merged.get("category") or "unknown"
                merged["category"] = category
                merged["category_label"] = VESSEL_TYPE_LABELS[category]
                merged["moving"] = (merged.get("sog") or 0) >= 0.5
                merged["age_basis"] = (
                    "源站观测时间" if observation else "本机接收时间")
                merged["age_minutes"] = max(
                    0.0, (now.timestamp() - age_time.timestamp()) / 60)
                rows.append(merged)
            rows.sort(key=lambda row: row["received_at"], reverse=True)
            if limit is not None:
                rows = rows[:limit]
            return deepcopy(rows)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "last_error": self._last_error,
                "last_message_at": self._last_message_at,
                "last_position_message_at": self._last_position_message_at,
                "last_raw_event_at": self._last_raw_event_at,
                "last_raw_message_type": self._last_raw_message_type,
                "last_rejection_reason": self._last_rejection_reason,
                "message_count": self._message_count,
                "raw_event_count": self._raw_event_count,
                "rejected_event_count": self._rejected_event_count,
                "position_message_count": self._position_message_count,
                "static_message_count": self._static_message_count,
                "connected_at": self._connected_at,
                "subscription_confirmed_at": self._subscription_confirmed_at,
                "compression_enabled": self._compression_enabled,
                "tracked_vessels": len(self._positions),
                "archive_error": self._archive_error,
                "archive_dropped_count": self._archive_dropped_count,
                "archive_unobserved_count": self._archive_unobserved_count,
                "archive_pending_count": len(self._archive_buffer),
            }
