"""Server-side collector state and archive orchestration."""

from __future__ import annotations

import json
import random
import threading
import time
from collections import deque
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable

from htfa.monitoring.energy_supply.data.stream_transport import websocket_connect
from htfa.monitoring.energy_supply.processing import ais


class AISCollector:
    """A reconnecting, thread-safe latest-position collector."""

    def __init__(
        self, api_key: str, connector: Callable[..., Any] | None = None
    ) -> None:
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
            target=self._archive_worker, name="ais-archive-writer", daemon=True
        )
        self._archive_thread.start()
        self._thread = threading.Thread(
            target=self._run, name="aisstream-collector", daemon=True
        )
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
                    ais.STREAM_URL,
                    open_timeout=10,
                    close_timeout=5,
                    ping_interval=20,
                    ping_timeout=20,
                    compression="deflate",
                    max_size=2 * 1024 * 1024,
                ) as socket:
                    connected_monotonic = time.monotonic()
                    with self._lock:
                        self._socket = socket
                    socket.send(json.dumps(ais.subscription(self._api_key)))
                    with self._lock:
                        self._status = "已连接，等待订阅确认"
                        self._connected_at = ais.utc_now().isoformat()
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
                                self._subscription_confirmed_at = (
                                    ais.utc_now().isoformat()
                                )
                                self._compression_enabled = compression_enabled
                            self._archive_wakeup.set()
                            continue
                        if event.get("error"):
                            raise RuntimeError(str(event["error"]))
                        self.ingest(event)
            except Exception as exc:
                self._archive_wakeup.set()
                if (
                    connected_monotonic is not None
                    and time.monotonic() - connected_monotonic >= 60
                ):
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
                batch = [
                    self._archive_buffer.popleft()
                    for _ in range(
                        min(ais.ARCHIVE_BATCH_SIZE, len(self._archive_buffer))
                    )
                ]
                should_stop = self._stop.is_set() and (not self._archive_buffer)
            if batch:
                try:
                    import htfa.monitoring.energy_supply.processing.ais_history as ais_history

                    ais_history.archive_reports(batch)
                    with self._lock:
                        self._archive_error = None
                except Exception as exc:
                    with self._lock:
                        self._archive_error = f"{type(exc).__name__}: {exc}"
                        for report in reversed(batch):
                            self._archive_buffer.appendleft(report)
                        while len(self._archive_buffer) > ais.MAX_ARCHIVE_BUFFER:
                            self._archive_buffer.pop()
                            self._archive_dropped_count += 1
                    if self._stop.is_set():
                        return
                    self._stop.wait(5)
            if should_stop:
                return

    def ingest(
        self, event: dict[str, Any], received_at: datetime | None = None
    ) -> bool:
        received = received_at or ais.utc_now()
        message_type = str(event.get("MessageType") or "缺失")
        with self._lock:
            self._raw_event_count += 1
            self._last_raw_event_at = received.isoformat()
            self._last_raw_message_type = message_type
        try:
            normalized = ais.normalize_event(event, received)
        except Exception as exc:
            with self._lock:
                self._rejected_event_count += 1
                self._last_rejection_reason = f"解析异常：{type(exc).__name__}"
            return False
        if normalized is None:
            reason = ais._normalization_rejection_reason(event)
            with self._lock:
                self._rejected_event_count += 1
                self._last_rejection_reason = reason
            return False
        normalized["data_source"] = "AISStream"
        normalized["source"] = "AISStream"
        normalized["source_url"] = ais.SOURCE
        normalized["source_attribution"] = "AISStream"
        mmsi = normalized["mmsi"]
        with self._lock:
            self._message_count += 1
            self._last_message_at = normalized["received_at"]
            if normalized["kind"] == "static":
                self._static_message_count += 1
                previous = self._static.get(mmsi, {})
                if not previous or ais._snapshot_is_newer(normalized, previous):
                    self._static[mmsi] = {
                        **previous,
                        **{
                            key: value
                            for key, value in normalized.items()
                            if value is not None
                        },
                    }
            else:
                self._position_message_count += 1
                self._last_position_message_at = normalized["received_at"]
                previous = self._positions.get(mmsi, {})
                if not previous or ais._snapshot_is_newer(normalized, previous):
                    self._positions[mmsi] = normalized
            self._ingest_since_prune += 1
            if self._ingest_since_prune >= 256:
                received_utc = ais.parse_utc(received.isoformat())
                self._prune_state_locked(
                    received_utc.timestamp() if received_utc else 0
                )
                self._ingest_since_prune = 0
        if normalized["kind"] == "position" and ais.in_collection_area(
            normalized["lat"], normalized["lon"]
        ):
            with self._lock:
                if normalized.get("observed_at"):
                    static = self._static.get(mmsi, {})
                    archive_row = {
                        **static,
                        **{
                            key: value
                            for key, value in normalized.items()
                            if value is not None
                        },
                    }
                    self._archive_buffer.append(archive_row)
                    if len(self._archive_buffer) > ais.MAX_ARCHIVE_BUFFER:
                        self._archive_buffer.popleft()
                        self._archive_dropped_count += 1
                    if len(self._archive_buffer) >= ais.ARCHIVE_BATCH_SIZE:
                        self._archive_wakeup.set()
                else:
                    self._archive_unobserved_count += 1
        return True

    def _prune_state_locked(self, now_timestamp: float) -> None:
        cutoff = now_timestamp - ais.POSITION_RETENTION_SECONDS
        stale = []
        for mmsi, position in self._positions.items():
            received = ais.parse_utc(position.get("received_at"))
            if received is None or received.timestamp() < cutoff:
                stale.append(mmsi)
        for mmsi in stale:
            self._positions.pop(mmsi, None)
            self._static.pop(mmsi, None)
        if len(self._positions) > ais.MAX_TRACKED_VESSELS:
            oldest = sorted(
                self._positions, key=lambda key: self._positions[key]["received_at"]
            )
            for mmsi in oldest[: len(self._positions) - ais.MAX_TRACKED_VESSELS]:
                self._positions.pop(mmsi, None)
                self._static.pop(mmsi, None)
        if len(self._static) > ais.MAX_TRACKED_VESSELS:
            oldest = sorted(
                self._static, key=lambda key: self._static[key].get("received_at", "")
            )
            for mmsi in oldest[: len(self._static) - ais.MAX_TRACKED_VESSELS]:
                self._static.pop(mmsi, None)

    def snapshot(
        self, max_age_minutes: int = 30, limit: int | None = None
    ) -> list[dict[str, Any]]:
        now = ais.utc_now()
        cutoff = now.timestamp() - max_age_minutes * 60
        with self._lock:
            rows = []
            for mmsi, position in self._positions.items():
                received = ais.parse_utc(position.get("received_at"))
                if received is None:
                    continue
                static = self._static.get(mmsi, {})
                merged = {
                    **position,
                    **{
                        key: value
                        for key, value in static.items()
                        if position.get(key) in (None, "")
                    },
                }
                if static.get("category"):
                    merged["category"] = static["category"]
                    merged["category_label"] = static["category_label"]
                    merged["ship_type_code"] = static.get("ship_type_code")
                observation = ais.parse_utc(merged.get("observed_at"))
                age_time = observation or received
                if age_time.timestamp() < cutoff:
                    continue
                category = merged.get("category") or "unknown"
                merged["category"] = category
                merged["category_label"] = ais.VESSEL_TYPE_LABELS[category]
                merged["moving"] = (merged.get("sog") or 0) >= 0.5
                merged["age_basis"] = "源站观测时间" if observation else "本机接收时间"
                merged["age_minutes"] = max(
                    0.0, (now.timestamp() - age_time.timestamp()) / 60
                )
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
