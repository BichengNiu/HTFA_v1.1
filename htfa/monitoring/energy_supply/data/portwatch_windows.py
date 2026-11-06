"""Validated PortWatch windows and persistent transport cache."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import zlib
from datetime import date, datetime, timezone
from pathlib import Path

from ..contracts.records import CHOKE_METRICS, PORT_METRICS
from . import portwatch_client as pw
from . import storage as data_store

logger = logging.getLogger(__name__)
VERSION = 1
PAGE_SIZE = 1000
BATCH_SIZE = 60
KINDS = {"ports": "港口", "chokepoints": "咽喉要道"}


class DownloadError(ValueError):
    pass


class CacheMiss(DownloadError):
    """A read-only page requested data that is not present in local cache."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day(value) -> date:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).date()
    return date.fromisoformat(str(value))


def _ids_where(ids: tuple[str, ...], kind: str) -> str:
    if kind not in ("ports", "chokepoints"):
        raise DownloadError("未知的PortWatch数据类型")
    valid = pw.valid_port_ids(ids) if kind == "ports" else pw.valid_chokepoint_ids(ids)
    if not ids or not valid or len(set(ids)) != len(ids):
        raise DownloadError("节点编号为空、重复或无效")
    return "portid IN (" + ",".join(f"'{pid}'" for pid in ids) + ")"


def bounds(kind: str, ids: tuple[str, ...]) -> tuple[dict, list[dict]]:
    if data_store.read_only():
        if not ids:
            return {}, []
        _ids_where(ids, kind)
        with data_store.connect() as conn:
            rows = conn.execute(
                "SELECT node_id,MIN(day),MAX(day),COUNT(*) FROM portwatch_daily "
                "WHERE kind=? AND node_id IN ("
                + ",".join("?" for _ in ids)
                + ") GROUP BY node_id",
                [kind, *ids],
            ).fetchall()
        return {
            pid: {
                "first": first.isoformat(),
                "last": last.isoformat(),
                "records": count,
            }
            for pid, first, last, count in rows
        }, [{"operation": "snapshot_node_date_bounds"}]
    output, queries = {}, []
    for offset in range(0, len(ids), BATCH_SIZE):
        batch = ids[offset : offset + BATCH_SIZE]
        where = _ids_where(batch, kind)
        statistics = [
            {
                "statisticType": "min",
                "onStatisticField": "date",
                "outStatisticFieldName": "first_date",
            },
            {
                "statisticType": "max",
                "onStatisticField": "date",
                "outStatisticFieldName": "last_date",
            },
            {
                "statisticType": "count",
                "onStatisticField": "ObjectId",
                "outStatisticFieldName": "records",
            },
        ]
        response = pw.query(
            pw.endpoint_for(kind),
            where=where,
            returnGeometry="false",
            outStatistics=json.dumps(statistics),
            groupByFieldsForStatistics="portid",
            resultRecordCount=PAGE_SIZE,
        )
        if response.get("exceededTransferLimit"):
            raise DownloadError("节点日期范围查询被截断")
        for item in response.get("features", []):
            row = item["attributes"]
            pid = row["portid"]
            if pid not in batch or pid in output:
                raise DownloadError("日期范围查询返回未请求或重复节点")
            first, last = _day(row["first_date"]), _day(row["last_date"])
            if (
                first > last
                or last > datetime.now(timezone.utc).date()
                or int(row["records"]) <= 0
            ):
                raise DownloadError("源站日期范围或记录数无效")
            output[pid] = {
                "first": first.isoformat(),
                "last": last.isoformat(),
                "records": int(row["records"]),
            }
        queries.append(
            {
                "endpoint": pw.endpoint_for(kind),
                "where": where,
                "operation": "node_date_bounds",
                "retrieved_at_utc": _now(),
            }
        )
    return output, queries


def _cache_path() -> Path:
    return data_store.database_path()


def _cache(
    key: str, payload: dict | None = None, max_age_seconds: int = 86400
) -> dict | None:
    """Cache only a validated complete query; a broken cache never hides source errors."""
    path = _cache_path()
    try:
        with data_store.connect(path) as conn:
            if payload is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO portwatch_cache VALUES (?, ?, ?)",
                    (
                        key,
                        datetime.now(timezone.utc).timestamp(),
                        zlib.compress(
                            json.dumps(
                                payload, ensure_ascii=False, allow_nan=False
                            ).encode()
                        ),
                    ),
                )
                conn.execute(
                    "DELETE FROM portwatch_cache WHERE saved < ?",
                    (datetime.now(timezone.utc).timestamp() - 7 * 86400,),
                )
                return None
            row = conn.execute(
                "SELECT saved,payload FROM portwatch_cache WHERE key=?", (key,)
            ).fetchone()
        if row and datetime.now(timezone.utc).timestamp() - row[0] < max_age_seconds:
            return json.loads(zlib.decompress(row[1]))
    except (OSError, data_store.duckdb.Error, ValueError, zlib.error) as exc:
        logger.warning(
            "PortWatch history cache unavailable (%s); continuing without it",
            type(exc).__name__,
        )
        pass
    return None


def fetch_window(
    kind: str,
    ids: tuple[str, ...],
    first: date,
    last: date,
    force: bool = False,
    progress=None,
    cache_revision: int | str = 0,
    cache_ttl_seconds: int = 86400,
    allow_stale: bool = False,
    cache_only: bool = False,
) -> tuple[list[dict], dict]:
    if data_store.read_only():
        _ids_where(ids, kind)
        rows = data_store.cached_portwatch_observations(kind, ids, first, last)
        return rows, {
            "cache_hit": True,
            "cache_source": "published DuckDB snapshot",
            "exported_query_rows": len(rows),
            "where": f"{first}/{last}",
            "scope": "local observations only; missing dates remain missing",
        }
    # The upstream field is DateOnly, not a timestamp; use ISO date strings.
    where = f"{_ids_where(ids, kind)} AND date >= '{first}' AND date <= '{last}'"
    endpoint = pw.endpoint_for(kind)
    metrics = PORT_METRICS if kind == "ports" else CHOKE_METRICS
    source_fields = (
        ["ObjectId", "date", "portid", "portname"]
        + (["country", "ISO3"] if kind == "ports" else [])
        + metrics
    )
    key = hashlib.sha256(
        json.dumps(
            [VERSION, endpoint, where, source_fields, cache_revision, cache_ttl_seconds]
        ).encode()
    ).hexdigest()
    cache_age = 7 * 86400 if allow_stale else cache_ttl_seconds
    cached = None if force else _cache(key, max_age_seconds=cache_age)
    if cached:
        try:
            cached_at = datetime.fromisoformat(
                str(cached["query"]["retrieved_at_utc"]).replace("Z", "+00:00")
            )
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            newest_fact = data_store.portwatch_window_latest_fetch(
                kind, ids, first, last
            )
        except (KeyError, TypeError, ValueError):
            newest_fact = None
            cached_at = None
        if cached_at is not None and (newest_fact is None or newest_fact <= cached_at):
            return cached["rows"], {**cached["query"], "cache_hit": True}
        if cached_at is not None:
            try:
                updates = data_store.cached_portwatch_rows_since(
                    kind, ids, first, last, cached_at
                )
            except Exception as exc:
                logger.warning(
                    "PortWatch newer local facts unavailable (%s)", type(exc).__name__
                )
                updates = []
            if updates:
                merged = {
                    (str(row.get("portid")), str(row.get("date"))[:10]): row
                    for row in cached["rows"]
                }
                for row in updates:
                    merged[(str(row["portid"]), str(row["date"])[:10])] = row
                merged_rows = [merged[key] for key in sorted(merged)]
                return merged_rows, {
                    **cached["query"],
                    "cache_hit": True,
                    "cache_source": "verified history with newer DuckDB facts",
                    "updated_local_rows": len(updates),
                    "source_count": len(merged_rows),
                    "exported_query_rows": len(merged_rows),
                }

    if not force:
        cached_rows = data_store.cached_portwatch_window(
            kind,
            ids,
            first,
            last,
            max_age_seconds=max(cache_ttl_seconds, 86_400),
            with_metadata=True,
            allow_stale=allow_stale,
        )
        if cached_rows is not None:
            local_rows, retrieved_at = cached_rows
            return local_rows, {
                "endpoint": endpoint,
                "where": where,
                "retrieved_at_utc": retrieved_at.isoformat(),
                "cache_hit": True,
                "cache_source": "DuckDB verified daily facts",
                "source_count": len(local_rows),
                "exported_query_rows": len(local_rows),
                "count_verified": True,
            }

    if cache_only:
        raise CacheMiss("本地PortWatch历史缓存缺失或不完整")

    expected_ids = None

    def count():
        nonlocal expected_ids
        if expected_ids is None:
            try:
                value = pw.query(
                    endpoint,
                    where=where,
                    returnGeometry="false",
                    returnCountOnly="true",
                )
                if "count" not in value:
                    raise DownloadError("源站未返回用于核对分页的总记录数")
                return int(value["count"])
            except pw.PortWatchQueryError:
                pass
        # The count handler can be broken while the same table's object-ID
        # operation works. IDs are unbounded by the feature page size in ArcGIS.
        value = pw.query(
            endpoint, where=where, returnGeometry="false", returnIdsOnly="true"
        )
        ids_value = value.get("objectIds")
        if (
            not isinstance(ids_value, list)
            or value.get("exceededTransferLimit")
            or any(
                not isinstance(item, int) or isinstance(item, bool) or item < 0
                for item in ids_value
            )
            or len(set(ids_value)) != len(ids_value)
        ):
            raise DownloadError("源站记录ID清单缺失、重复或被截断")
        current_ids = set(ids_value)
        if expected_ids is not None and current_ids != expected_ids:
            raise DownloadError("源站记录ID清单在分页期间变化")
        expected_ids = current_ids
        return len(expected_ids)

    expected = count()
    rows, keys, object_ids = [], set(), set()
    offset = 0
    while offset < expected:
        page = pw.query(
            endpoint,
            where=where,
            returnGeometry="false",
            outFields=",".join(source_fields),
            orderByFields="ObjectId ASC",
            resultOffset=offset,
            resultRecordCount=PAGE_SIZE,
        )
        items = page.get("features", [])
        if not items:
            raise DownloadError(
                f"{KINDS[kind]} {first}—{last} 分页提前结束（{offset}/{expected}）"
            )
        for item in items:
            row = dict(item["attributes"])
            if row.get("ObjectId") is not None:
                if row["ObjectId"] in object_ids:
                    raise DownloadError("源站分页返回重复记录ID")
                object_ids.add(row["ObjectId"])
            day = _day(row.get("date"))
            pid = row.get("portid")
            record_key = (pid, day)
            if pid not in ids or not first <= day <= last or record_key in keys:
                raise DownloadError(f"返回重复或超出请求范围的记录：{pid}/{day}")
            for metric in metrics:
                value = row.get(metric)
                if value is not None and (
                    not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise DownloadError(f"{pid}/{day} 的{metric}不是有效非负数值")
            row["date"] = day.isoformat()
            row.pop("ObjectId", None)
            rows.append(row)
            keys.add(record_key)
        offset += len(items)
        if progress:
            progress(f"{KINDS[kind]} {first}—{last}：{offset:,}/{expected:,} 条")
    if len(rows) != expected or count() != expected:
        raise DownloadError(
            f"{KINDS[kind]} {first}—{last} 源记录数发生变化或分页不完整，请重新生成"
        )
    if expected_ids is not None and object_ids != expected_ids:
        raise DownloadError("分页记录与源站ID清单不一致")
    data_store.save_portwatch(kind, rows, endpoint)
    query = {
        "endpoint": endpoint,
        "where": where,
        "out_fields": source_fields,
        "retrieved_at_utc": _now(),
        "cache_hit": False,
        "source_count": expected,
        "exported_query_rows": len(rows),
        "count_verified": True,
        "count_method": "object_ids" if expected_ids is not None else "count",
    }
    _cache(key, {"rows": rows, "query": query})
    return rows, query
