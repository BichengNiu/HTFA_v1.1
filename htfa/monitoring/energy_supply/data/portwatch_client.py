"""ArcGIS transport, evidence retention, throttling and request deadlines."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import storage as data_store

ROOT = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS = f"{ROOT}/PortWatch_ports_database/FeatureServer/0/query"
DAILY = f"{ROOT}/Daily_Ports_Data/FeatureServer/0/query"
CHOKEPOINTS = f"{ROOT}/PortWatch_chokepoints_database/FeatureServer/0/query"
CHOKEPOINT_DAILY = f"{ROOT}/Daily_Chokepoints_Data/FeatureServer/0/query"
SPILLOVERS = f"{ROOT}/spillovers_port_level_impact/FeatureServer/0/query"
SOURCE = "https://portwatch.imf.org/pages/data-and-methodology"
MODULE_VERSION = 9
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST = 0.0
_REQUEST_DEADLINE = ContextVar("portwatch_request_deadline", default=None)
QUERY_ATTEMPTS = 6


class PortWatchQueryError(ValueError):
    """An upstream ArcGIS query failed; no empty observations are implied."""


class RequestBudgetExceeded(TimeoutError):
    """A caller-wide deadline expired while fetching a PortWatch snapshot."""


@contextmanager
def request_budget(seconds: float | None):
    """Apply one wall-clock budget across every query in the current operation."""
    current = _REQUEST_DEADLINE.get()
    deadline = current
    if seconds is not None:
        candidate = time.monotonic() + max(0.0, float(seconds))
        deadline = candidate if current is None else min(current, candidate)
    token = _REQUEST_DEADLINE.set(deadline)
    try:
        yield
    finally:
        _REQUEST_DEADLINE.reset(token)


def _remaining_budget() -> float | None:
    deadline = _REQUEST_DEADLINE.get()
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RequestBudgetExceeded("PortWatch请求超过本次操作总时限")
    return remaining


def _budget_sleep(seconds: float) -> None:
    remaining = _remaining_budget()
    if remaining is not None and seconds >= remaining:
        raise RequestBudgetExceeded("PortWatch请求超过本次操作总时限")
    time.sleep(seconds)


def query(url: str, **params: object) -> dict:
    """Read one ArcGIS response and surface source-reported errors."""
    if data_store.read_only():
        raise RuntimeError("只读展示端不允许请求 PortWatch；请由采集任务更新快照")
    global _LAST_REQUEST
    for attempt in range(QUERY_ATTEMPTS):
        options = dict(params)
        if attempt in (1, 2, 3):
            options.update(sqlFormat="standard", timeReferenceUnknownClient="true")
        options["f"] = "pjson" if attempt in (2, 4) else "json"
        if attempt >= 4:
            options["_retry"] = uuid.uuid4().hex
        encoded = urlencode(options).encode()
        headers = {"User-Agent": "oil-field-map-demo/1.0", "Cache-Control": "no-cache"}
        request = (
            Request(url, data=encoded, headers=headers)
            if attempt == 3
            else Request(f"{url}?{encoded.decode()}", headers=headers)
        )
        with _REQUEST_LOCK:
            remaining_budget = _remaining_budget()
            remaining = 0.5 - (time.monotonic() - _LAST_REQUEST)
            if remaining > 0:
                if remaining_budget is not None and remaining >= remaining_budget:
                    raise RequestBudgetExceeded("PortWatch请求超过本次操作总时限")
                time.sleep(remaining)
            remaining_budget = _remaining_budget()
            _LAST_REQUEST = time.monotonic()
        try:
            timeout = 35 if remaining_budget is None else min(35, remaining_budget)
            with urlopen(request, timeout=timeout) as response:
                result = json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise
            result = {
                "error": {
                    "message": "Too many requests" if exc.code == 429 else str(exc),
                    "code": exc.code,
                }
            }
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            result = {"error": {"message": str(exc), "code": 503}}
        error = result.get("error")
        if not error:
            if attempt:
                logging.getLogger(__name__).info(
                    "PortWatch query recovered: attempt=%s method=%s format=%s endpoint=%s",
                    attempt + 1,
                    request.get_method(),
                    options["f"],
                    url,
                )
            return result
        message = str(error.get("message", error))
        throttled = "too many requests" in message.lower()
        # ArcGIS also emits this generic backend error for valid queries that
        # subsequently succeed unchanged. Retry it within the same time budget;
        # a persistent error still aborts publication, never becomes an empty set.
        query_backend_error = error.get("code") in (400, 500, 502, 503, 504) and (
            message == "Cannot perform query. Invalid query parameters."
            or message == "Invalid URL"
            or "object reference not set" in message.lower()
            or error.get("code") in (500, 502, 503, 504)
            or "Unable to perform query. Please check your parameters."
            in error.get("details", [])
        )
        if not (throttled or query_backend_error) or attempt == QUERY_ATTEMPTS - 1:
            context = {
                key: params[key]
                for key in (
                    "where",
                    "outFields",
                    "outStatistics",
                    "groupByFieldsForStatistics",
                    "returnCountOnly",
                    "resultOffset",
                    "resultRecordCount",
                )
                if key in params
            }
            raise PortWatchQueryError(
                f"PortWatch API: {message}; details={error.get('details', [])}; "
                f"endpoint={url}; query={json.dumps(context, ensure_ascii=False)}"
            )
        _budget_sleep(
            (5, 15, 20, 25, 30)[attempt] if throttled else (1, 2, 3, 5, 8)[attempt]
        )
    raise ValueError("PortWatch请求未完成")


def endpoint_for(kind: str) -> str:
    if kind == "ports":
        return DAILY
    if kind == "chokepoints":
        return CHOKEPOINT_DAILY
    raise ValueError("未知的 PortWatch 数据类型")


def valid_port_ids(ids: tuple[str, ...]) -> bool:
    """Validate source-backed port identifiers at module boundaries."""
    return all(re.fullmatch(r"(?:port|fso)\d+", port_id) for port_id in ids)


def valid_chokepoint_ids(ids: tuple[str, ...]) -> bool:
    """Validate source-backed chokepoint identifiers at module boundaries."""
    return all(re.fullmatch(r"chokepoint\d+", point_id) for point_id in ids)
