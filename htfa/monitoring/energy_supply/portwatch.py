"""IMF PortWatch port and chokepoint indicators for the map.

The region boxes are an explicit, editable definition of "near" the five waters.
The catalog also includes source-backed supplementary ports with unknown activity.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import streamlit as st
from htfa.monitoring.energy_supply import port_inventory
from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply.regions import MONITORED_REGIONS, region_for
from htfa.monitoring.energy_supply.portwatch_records import SHIP_TYPES, PORT_METRICS, CHOKE_METRICS

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

FOCUS_CHOKEPOINT_IDS = ("chokepoint1", "chokepoint4", "chokepoint6")
CHOKEPOINT_LABELS = {
    "chokepoint1": "苏伊士运河",
    "chokepoint4": "曼德海峡",
    "chokepoint6": "霍尔木兹海峡",
}


def valid_port_ids(ids: tuple[str, ...]) -> bool:
    """Validate source-backed port identifiers at module boundaries."""
    return all(re.fullmatch(r"(?:port|fso)\d+", port_id) for port_id in ids)


def has_independent_statistics(port: dict) -> bool:
    """Return whether a catalog point has a supported PortWatch activity ID."""
    if "statistics_available" in port:
        return bool(port["statistics_available"])
    return valid_port_ids((str(port.get("portid", "")),))


def _activity_ids(ids: tuple[str, ...]) -> tuple[str, ...]:
    unknown = [pid for pid in ids if not valid_port_ids((pid,))
               and pid not in port_inventory.SUPPLEMENTAL_IDS]
    if unknown:
        raise ValueError("无效或未登记的港口编号")
    return tuple(pid for pid in ids if valid_port_ids((pid,)))


def valid_chokepoint_ids(ids: tuple[str, ...]) -> bool:
    """Validate source-backed chokepoint identifiers at module boundaries."""
    return all(re.fullmatch(r"chokepoint\d+", point_id) for point_id in ids)


# south, north, west, east. Order assigns ports in overlapping boxes only once.
REGIONS = MONITORED_REGIONS


def query(url: str, **params: object) -> dict:
    """Read one ArcGIS response and surface source-reported errors."""
    if data_store.read_only():
        raise RuntimeError("只读展示端不允许请求 PortWatch；请由采集任务更新快照")
    global _LAST_REQUEST
    for attempt in range(QUERY_ATTEMPTS):
        options = dict(params)
        if attempt in (1, 2, 3):
            options.update(sqlFormat='standard', timeReferenceUnknownClient='true')
        options['f'] = 'pjson' if attempt in (2, 4) else 'json'
        if attempt >= 4:
            options['_retry'] = uuid.uuid4().hex
        encoded = urlencode(options).encode()
        headers = {'User-Agent': 'oil-field-map-demo/1.0', 'Cache-Control': 'no-cache'}
        request = (Request(url, data=encoded, headers=headers) if attempt == 3 else
                   Request(f'{url}?{encoded.decode()}', headers=headers))
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
            result = {'error': {'message': 'Too many requests' if exc.code == 429 else str(exc), 'code': exc.code}}
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            result = {'error': {'message': str(exc), 'code': 503}}
        error = result.get("error")
        if not error:
            if attempt:
                logging.getLogger(__name__).info(
                    'PortWatch query recovered: attempt=%s method=%s format=%s endpoint=%s',
                    attempt + 1, request.get_method(), options['f'], url)
            return result
        message = str(error.get("message", error))
        throttled = "too many requests" in message.lower()
        # ArcGIS also emits this generic backend error for valid queries that
        # subsequently succeed unchanged. Retry it within the same time budget;
        # a persistent error still aborts publication, never becomes an empty set.
        query_backend_error = error.get("code") in (400, 500, 502, 503, 504) and (
            message == "Cannot perform query. Invalid query parameters."
            or message == 'Invalid URL'
            or 'object reference not set' in message.lower()
            or error.get('code') in (500, 502, 503, 504)
            or "Unable to perform query. Please check your parameters." in error.get("details", []))
        if not (throttled or query_backend_error) or attempt == QUERY_ATTEMPTS - 1:
            context = {key: params[key] for key in (
                "where", "outFields", "outStatistics", "groupByFieldsForStatistics",
                "returnCountOnly", "resultOffset", "resultRecordCount") if key in params}
            raise PortWatchQueryError(f"PortWatch API: {message}; details={error.get('details', [])}; "
                             f"endpoint={url}; query={json.dumps(context, ensure_ascii=False)}")
        _budget_sleep((5, 15, 20, 25, 30)[attempt] if throttled else (1, 2, 3, 5, 8)[attempt])
    raise ValueError("PortWatch请求未完成")


def endpoint_for(kind: str) -> str:
    if kind == "ports":
        return DAILY
    if kind == "chokepoints":
        return CHOKEPOINT_DAILY
    raise ValueError("未知的 PortWatch 数据类型")


GULF_COUNTRIES = ("Bahrain", "Iran", "Iraq", "Kuwait", "Oman", "Qatar",
                  "Saudi Arabia", "United Arab Emirates")
# Extra coastlines apply to the eight producers; AIS watch boxes stay separate.
GULF_PORT_REGIONS = {
    "红海沿岸": (15.4, 30.0, 32.0, 44.0),
    "阿拉伯海": (15.0, 22.0, 50.0, 62.0),
    "里海": (35.0, 39.0, 48.0, 56.0),
}


def port_region_for(lat: float, lon: float) -> str | None:
    region = region_for(lat, lon)
    if region:
        return region
    return region_for(lat, lon, GULF_PORT_REGIONS)


@st.cache_data(ttl=24 * 3600, max_entries=12, show_spinner=False)
def port_catalog(refresh_revision: str = "initial") -> list[dict]:
    from htfa.monitoring.energy_supply.port_metadata import PORT_COUNTRIES
    # Fetch each selected country's full coastline, independent of AIS boxes.
    where = "country IN (" + ",".join(
        f"'{country}'" for country in sorted(PORT_COUNTRIES)) + ")"
    found = []
    offset = 0
    while True:
        page = query(PORTS, where=where, outFields="portid,portname,country,lat,lon",
                      returnGeometry="false", resultOffset=offset, resultRecordCount=1000,
                      orderByFields="portid ASC")
        items = page.get("features", [])
        found.extend(item["attributes"] for item in items)
        if not page.get("exceededTransferLimit") and len(items) < 1000:
            break
        if not items:
            raise ValueError("PortWatch点位分页未前进")
        offset += len(items)
    if len({item["portid"] for item in found}) != len(found):
        raise ValueError("PortWatch点位库出现重复编号")
    ports = []
    for item in found:
        if item["lat"] is None or item["lon"] is None:
            continue
        region = port_region_for(item["lat"], item["lon"])
        if region is None:
            region = "其他沿岸（水域待核）"
        if region:
            ports.append({"portid": item["portid"], "name": item["portname"],
                          "country": item["country"], "lat": item["lat"],
                          "lon": item["lon"], "region": region})
    enriched = port_inventory.enrich(ports)
    data_store.save_catalog("ports", enriched)
    return data_store.load_catalog("ports")


def _latest_day(endpoint: str, missing_message: str) -> date:
    try:
        data = query(endpoint, where="1=1", returnGeometry="false",
                     outStatistics=json.dumps([{"statisticType": "max", "onStatisticField": "date",
                                                "outStatisticFieldName": "latest_date"}]))
        field = 'latest_date'
    except PortWatchQueryError:
        # A DateOnly statistics handler can fail while ordinary table reads
        # remain available. Descending order with a single row is the same max.
        data = query(endpoint, where='1=1', returnGeometry='false', outFields='date',
                     orderByFields='date DESC', resultRecordCount=1)
        field = 'date'
    value = data['features'][0]['attributes'][field] if data.get('features') else None
    if not value:
        raise ValueError(missing_message)
    day = date.fromisoformat(value)
    if day > date.today():
        raise ValueError('PortWatch返回未来数据日期')
    return day


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def latest_date(refresh_revision: str = "initial") -> date:
    return _latest_day(DAILY, "PortWatch 尚无可用日期")


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def _activity_rows(day: date, port_ids: tuple[str, ...], calendar_days: int,
                   refresh_revision: str = "initial",
                   data_revision: int = 0) -> dict[str, dict[date, dict]]:
    """Fetch one validated daily window for reuse by latest-day and rolling indicators."""
    grouped: dict[str, dict[date, dict]] = {port_id: {} for port_id in port_ids}
    port_ids = tuple(sorted(set(_activity_ids(port_ids))))
    if calendar_days < 1:
        raise ValueError("活动数据窗口天数无效")
    first_day = day - timedelta(days=calendar_days - 1)
    if refresh_revision == "initial":
        cached_rows = data_store.cached_portwatch_observations(
            "ports", port_ids, first_day, day)
        for values in cached_rows:
            grouped[values["portid"]][date.fromisoformat(values["date"])] = values
        return grouped
    for start in range(0, len(port_ids), 80):
        ids = port_ids[start:start + 80]
        if not valid_port_ids(ids):
            raise ValueError("无效的 PortWatch 港口编号")
        quoted = ",".join(f"'{p}'" for p in ids)
        # ArcGIS esriFieldTypeDateOnly accepts ISO date strings. DATE literals
        # can fail with code 400 even for otherwise valid node/date windows.
        where = (f"date >= '{first_day.isoformat()}' AND date <= '{day.isoformat()}' "
                 f"AND portid IN ({quoted})")
        count_before = query(DAILY, where=where, returnGeometry="false",
                              returnCountOnly="true").get("count")
        if count_before is None:
            raise ValueError("PortWatch未返回用于核对分页的记录总数")
        expected_count = int(count_before)
        offset = 0
        fetched_count = 0
        while True:
            page = query(DAILY, where=where, returnGeometry="false", resultOffset=offset,
                          resultRecordCount=1000, orderByFields="portid ASC,date ASC",
                          outFields=",".join(["date", "portid", "portname", "country", "ISO3", *PORT_METRICS]))
            items = page.get("features", [])
            exceeded = bool(page.get("exceededTransferLimit"))
            if exceeded and not items:
                raise ValueError("PortWatch活动数据分页被截断且未前进")
            fetched_count += len(items)
            for item in items:
                values = item["attributes"]
                port_id = values.get("portid")
                value_day = date.fromisoformat(values["date"])
                if port_id not in grouped or not first_day <= value_day <= day:
                    raise ValueError("PortWatch返回窗口之外或未请求的记录")
                if value_day in grouped[port_id]:
                    raise ValueError(f"PortWatch重复港口/日期：{port_id}/{value_day}")
                grouped[port_id][value_day] = values
            if not exceeded and len(items) < 1000:
                break
            offset += len(items)
        count_after = query(DAILY, where=where, returnGeometry="false",
                             returnCountOnly="true").get("count")
        if fetched_count != expected_count or count_after != expected_count:
            raise ValueError(
                f"PortWatch活动数据分页不完整或源记录变化：{fetched_count}/{expected_count}")
    data_store.save_portwatch("ports", [row for rows in grouped.values() for row in rows.values()], DAILY)
    return grouped


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def daily_activity(day: date, port_ids: tuple[str, ...],
                   refresh_revision: str = "initial",
                   data_revision: int = 0) -> dict[str, dict]:
    # Reuse the same two-week response as the default rolling indicators.
    rows = _activity_rows(day, port_ids, max(14, day.day), refresh_revision, data_revision)
    return {port_id: values[day] for port_id, values in rows.items() if day in values}


def _complete_sum(rows: list[dict], days: int, *fields: str) -> float | None:
    """Only sum a complete window; a reported zero remains a numeric value."""
    if len(rows) != days or any(row.get(field) is None for row in rows for field in fields):
        return None
    return sum(sum(row[field] for field in fields) for row in rows)


@st.cache_data(ttl=3600, max_entries=24, show_spinner=False)
def week_to_date_activity(day: date, port_ids: tuple[str, ...],
                          refresh_revision: str = "initial", data_revision: int = 0) -> dict[str, dict]:
    """Sum Monday through the source day; partial weeks require all elapsed days."""
    ids = tuple(_activity_ids(port_ids))
    first = day - timedelta(days=day.weekday())
    expected = day.weekday() + 1
    # Share the existing daily lookup's cached local read, without another query.
    grouped = _activity_rows(day, ids, max(14, day.day), refresh_revision, data_revision)
    summary = {}
    for pid in port_ids:
        values = [row for observed, row in grouped.get(pid, {}).items() if first <= observed <= day]
        total = _complete_sum(values, expected, "portcalls")
        result = {"week_start": first.isoformat(), "week_end": day.isoformat(),
                  "week_expected_days": expected, "week_observed_days": len(values), "week_calls": total}
        for kind in SHIP_TYPES:
            calls = _complete_sum(values, expected, f"portcalls_{kind}")
            result[f"week_calls_{kind}"] = calls
            result[f"week_share_{kind}"] = calls / total * 100 if calls is not None and total else None
        month = [row for observed,row in grouped.get(pid, {}).items() if day.replace(day=1)<=observed<=day]
        result["month_calls"] = _complete_sum(month, day.day, "portcalls")
        for kind in SHIP_TYPES:
            result[f"month_calls_{kind}"] = _complete_sum(month, day.day, f"portcalls_{kind}")
        summary[pid] = result
    return summary


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def rolling_activity(day: date, port_ids: tuple[str, ...], days: int = 7,
                     refresh_revision: str = "initial",
                     data_revision: int = 0) -> dict[str, dict]:
    """Return complete-window port indicators and the preceding-window baseline.

    Do not turn missing days into zeros; keep raw zero-valued source records.
    """
    if days not in (7, 30):
        raise ValueError("仅支持 7 天或 30 天窗口")
    requested_ids = tuple(port_ids)
    port_ids = _activity_ids(port_ids)
    current_first = day - timedelta(days=days - 1)
    previous_first = day - timedelta(days=2 * days - 1)
    previous_last = current_first - timedelta(days=1)
    grouped = _activity_rows(day, port_ids, 2 * days, refresh_revision, data_revision)
    for port_id in requested_ids:
        grouped.setdefault(port_id, {})
    summary = {}
    for port_id, by_day in grouped.items():
        values = [value for value_day, value in by_day.items()
                  if current_first <= value_day <= day]
        previous = [value for value_day, value in by_day.items()
                    if previous_first <= value_day <= previous_last]
        current_complete = len(values) == days
        total_calls = _complete_sum(values, days, "portcalls")
        def positive_days(field):
            return (sum(v[field] > 0 for v in values)
                    if current_complete and all(v.get(field) is not None for v in values) else None)
        result = {"observed_days": len(values), "previous_observed_days": len(previous),
                  "window_days": days, "active_days": positive_days("portcalls"),
                  "tanker_positive_days": positive_days("portcalls_tanker"),
                  "cargo_positive_days": positive_days("portcalls_cargo"),
                  "tanker_calls_zero_volume_days": (sum(
                      v["portcalls_tanker"] > 0 and v["import_tanker"] + v["export_tanker"] == 0
                      for v in values) if current_complete and all(v.get(f) is not None
                      for v in values for f in ("portcalls_tanker", "import_tanker", "export_tanker")) else None)}
        for kind in (*SHIP_TYPES, "cargo"):
            call_field, import_field, export_field = (f"portcalls_{kind}", f"import_{kind}", f"export_{kind}")
            calls = _complete_sum(values, days, call_field)
            handled = _complete_sum(values, days, import_field, export_field)
            result[f"avg_calls_{kind}"] = calls / days if calls is not None else None
            result[f"avg_handled_{kind}"] = handled / days if handled is not None else None
            result[f"window_calls_{kind}"] = calls

        total_import = _complete_sum(values, days, "import")
        total_export = _complete_sum(values, days, "export")
        previous_calls = _complete_sum(previous, days, "portcalls")
        result["window_calls"] = total_calls
        result["avg_calls"] = total_calls / days if total_calls is not None else None
        result["avg_handled"] = ((total_import + total_export) / days
                                 if total_import is not None and total_export is not None else None)
        result["active_day_rate"] = (result["active_days"] / days * 100
                                     if total_calls is not None else None)
        result["average_cargo_per_call"] = (
            (total_import + total_export) / total_calls
            if total_calls and total_import is not None and total_export is not None else None)
        total_trade = ((total_import + total_export)
                       if total_import is not None and total_export is not None else None)
        result["trade_balance_index"] = (
            (total_export - total_import) / total_trade * 100 if total_trade else None)
        result["activity_index"] = (
            total_calls / previous_calls * 100
            if total_calls is not None and previous_calls else None)
        result["window_import"] = total_import
        result["window_export"] = total_export
        for kind in SHIP_TYPES:
            kind_calls = result.get(f"window_calls_{kind}")
            result[f"share_{kind}"] = (
                kind_calls / total_calls * 100
                if kind_calls is not None and total_calls else None)
        summary[port_id] = result
    return summary


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def port_risk_capacity(port_ids: tuple[str, ...], refresh_revision: str = "initial") -> dict[str, float | None]:
    """Aggregate historical daily at-risk capacity over each port's outbound routes."""
    totals: dict[str, float | None] = {port_id: None for port_id in port_ids}
    port_ids = _activity_ids(port_ids)
    statistic = json.dumps([{
        "statisticType": "sum", "onStatisticField": "daily_capacity_at_risk",
        "outStatisticFieldName": "risk_capacity",
    }])
    for start in range(0, len(port_ids), 80):
        ids = port_ids[start:start + 80]
        if not valid_port_ids(ids):
            raise ValueError("无效的 PortWatch 港口编号")
        quoted = ",".join(f"'{port_id}'" for port_id in ids)
        where = f"from_portid IN ({quoted})"
        page = query(SPILLOVERS, where=where, returnGeometry="false",
                      groupByFieldsForStatistics="from_portid", outStatistics=statistic,
                      orderByFields="from_portid ASC", outFields="from_portid")
        for item in page.get("features", []):
            value = item["attributes"]
            capacity = value.get("risk_capacity")
            totals[value["from_portid"]] = float(capacity) if capacity is not None else None
    return totals


@st.cache_data(ttl=24 * 3600, max_entries=12, show_spinner=False)
def chokepoint_catalog(refresh_revision: str = "initial") -> list[dict]:
    ids = FOCUS_CHOKEPOINT_IDS
    quoted = ",".join(f"'{point_id}'" for point_id in ids)
    page = query(CHOKEPOINTS, where=f"portid IN ({quoted})", returnGeometry="false",
                  outFields="portid,portname,fullname,lat,lon", resultRecordCount=100)
    found = {item["attributes"]["portid"]: item["attributes"]
             for item in page.get("features", [])}
    output = []
    for point_id in ids:
        if point_id in found:
            row = dict(found[point_id])
            row["name_cn"] = CHOKEPOINT_LABELS[point_id]
            output.append(row)
    data_store.save_catalog("chokepoints", output)
    return data_store.load_catalog("chokepoints")


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def latest_chokepoint_date(refresh_revision: str = "initial") -> date:
    return _latest_day(CHOKEPOINT_DAILY, "PortWatch 尚无可用咽喉点日期")


@st.cache_data(ttl=3600, max_entries=12, show_spinner=False)
def chokepoint_activity(day: date, chokepoint_ids: tuple[str, ...],
                        refresh_revision: str = "initial",
                        data_revision: int = 0) -> dict[str, dict]:
    if not valid_chokepoint_ids(chokepoint_ids):
        raise ValueError("无效的 PortWatch 咽喉点编号")
    if refresh_revision == "initial":
        cached_rows = data_store.cached_portwatch_observations(
            "chokepoints", chokepoint_ids, day, day)
        return {row["portid"]: row for row in cached_rows}
    quoted = ",".join(f"'{point_id}'" for point_id in chokepoint_ids)
    where = f"date = '{day.isoformat()}' AND portid IN ({quoted})"
    page = query(
        CHOKEPOINT_DAILY, where=where, returnGeometry="false", resultRecordCount=100,
        orderByFields="portid ASC,date ASC",
        outFields=",".join(["date", "portid", "portname", *CHOKE_METRICS]))
    if page.get("exceededTransferLimit"):
        raise ValueError("PortWatch咽喉点最新数据被截断")
    result = {}
    for item in page.get("features", []):
        value = item["attributes"]
        if value["portid"] in result:
            raise ValueError(f"PortWatch 咽喉点日活动出现重复记录：{value['portid']}")
        result[value["portid"]] = value
    data_store.save_portwatch("chokepoints", list(result.values()), CHOKEPOINT_DAILY)
    return result


def decorate_chokepoints(points: list[dict], activity: dict[str, dict]) -> list[dict]:
    output = []
    for point in points:
        row = dict(point)
        values = activity.get(point["portid"])
        row["has_data"] = values is not None
        if values:
            row.update(values)
        output.append(row)
    return output


def decorate(ports: list[dict], activity: dict[str, dict],
             rolling: dict[str, dict] | None = None,
             risk_capacity: dict[str, float] | None = None) -> list[dict]:
    output = []
    for port in ports:
        row = dict(port)
        values = activity.get(port["portid"])
        row["has_data"] = values is not None
        if rolling is not None:
            row.update(rolling.get(port["portid"], {}))
        if risk_capacity is not None:
            row["risk_capacity"] = risk_capacity.get(port["portid"])
        if values:
            row.update({key: values.get(key) for key in (
                "portcalls", "portcalls_container", "portcalls_dry_bulk",
                "portcalls_general_cargo", "portcalls_roro", "portcalls_tanker",
                "portcalls_cargo", "import", "export", "import_tanker",
                "export_tanker", "import_cargo", "export_cargo")})
            # 'cargo' is the PortWatch non-tanker vessel category, including
            # container, dry bulk, general cargo and Ro-Ro. Do not sum with tanker.
            # Missing observations stay missing; an observed zero stays zero.
            for kind in ("tanker", "cargo"):
                imported, exported = row[f"import_{kind}"], row[f"export_{kind}"]
                row[f"handled_{kind}"] = (imported + exported
                                           if imported is not None and exported is not None else None)
            row["handled"] = (row["import"] + row["export"]
                              if row["import"] is not None and row["export"] is not None else None)
        output.append(row)
    return output
