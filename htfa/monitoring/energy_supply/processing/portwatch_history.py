from htfa.monitoring.energy_supply.data import queries

"""Repair node/day holes from the retained archive start, with source evidence.

Only verified empty upstream results may remain missing; never manufacture zeros.
"""
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import date, datetime, timedelta, timezone

import htfa.monitoring.energy_supply.data.storage as data_store
from htfa.monitoring.energy_supply.processing import catalogs

AUDIT_PREFIX = "portwatch_history_coverage:"
SOURCE_GAP_TTL = timedelta(days=7)
MAX_CHUNK_DAYS = 90
ARCHIVE_START = date(2019, 1, 1)
logger = logging.getLogger(__name__)


def _dates(first, last):
    for offset in range((last - first).days + 1):
        yield first + timedelta(days=offset)


def _intervals(days):
    first = previous = None
    for day in sorted(days):
        if previous is not None and day != previous + timedelta(days=1):
            yield first, previous
            first = None
        if first is None:
            first = day
        previous = day
    if first is not None:
        yield first, previous


def _ids(kind):
    return tuple(sorted(str(row["portid"]) for row in catalogs.load_catalog(kind)
                        if kind == "chokepoints" or row.get("statistics_available", bool(
                            re.fullmatch(r"(?:port|fso)\d+", str(row.get("portid", "")))))))


def _state(kind, ids=None, end=None):
    ids = _ids(kind) if ids is None else tuple(sorted(set(ids)))
    audit = data_store.meta(AUDIT_PREFIX + kind, {})
    earliest, latest = queries.portwatch_date_bounds(kind)
    if end is None:
        end = max(filter(None, (latest, date.fromisoformat(audit["last_day"])
                                if audit.get("last_day") else None)), default=None)
    if not ids or end is None:
        raise ValueError(f"{kind} 缺少历史范围或统计节点")
    first = min(filter(None, (earliest, ARCHIVE_START,
                              date.fromisoformat(audit["first_day"])
                              if audit.get("first_day") else None)))
    stored = queries.portwatch_keys(kind, ids, first, end)
    expected = {(node, day) for node in ids for day in _dates(first, end)}
    return {"kind": kind, "ids": ids, "first": first, "last": end,
            "expected": expected, "missing": expected - stored, "audit": audit}


def _verified_missing(audit, now):
    verified = {}
    for gap in audit.get("source_missing", []):
        checked = datetime.fromisoformat(gap["verified_at"])
        if timedelta(0) <= now - checked < SOURCE_GAP_TTL:
            for day in _dates(date.fromisoformat(gap["first"]), date.fromisoformat(gap["last"])):
                verified[gap["node_id"], day] = checked
    return verified


def _report(state, verified):
    missing = state["missing"]
    unverified = missing - verified.keys()
    return {"first_day": state["first"].isoformat(), "last_day": state["last"].isoformat(),
            "nodes": len(state["ids"]), "expected_records": len(state["expected"]),
            "stored_records": len(state["expected"]) - len(missing),
            "source_missing_records": len(missing) - len(unverified),
            "unverified_missing_records": len(unverified),
            "status": "unverified_gaps" if unverified else "source_gaps" if missing else "complete"}


def needs_repair(now=None, kind=None):
    now = now or datetime.now(timezone.utc)
    for kind in ((kind,) if kind is not None else ("ports", "chokepoints")):
        try:
            state = _state(kind)
        except ValueError:
            return True
        if not state["audit"] or state["missing"] - _verified_missing(state["audit"], now).keys():
            return True
    return False


def repair(kind, ids, end, now=None):
    import htfa.monitoring.energy_supply.data.portwatch_windows as portwatch_downloads
    now = now or datetime.now(timezone.utc)
    state = _state(kind, ids, end)
    verified = _verified_missing(state["audit"], now)
    unknown = state["missing"] - verified.keys()
    by_node = defaultdict(set)
    for node, day in unknown:
        by_node[node].add(day)
    batches = defaultdict(list)
    for node, days in by_node.items():
        for first, last in _intervals(days):
            while first <= last:
                stop = min(last, first + timedelta(days=MAX_CHUNK_DAYS - 1))
                batches[first, stop].append(node)
                first = stop + timedelta(days=1)
    def download(first, last, chunk):
        rows, query = portwatch_downloads.fetch_window(kind, chunk, first, last, force=True)
        if not query.get("count_verified"):
            raise ValueError(f"{kind} 历史补缺未完成上游记录数校验")
        keys = {(str(row["portid"]), date.fromisoformat(str(row["date"])[:10])) for row in rows}
        if len(keys) != len(rows) or any(node not in chunk or not first <= day <= last for node, day in keys):
            raise ValueError(f"{kind} 历史补缺返回重复或越界记录")
        stored = queries.portwatch_keys(kind, chunk, first, last)
        if not keys <= stored:
            raise ValueError(f"{kind} 上游已返回记录但未成功入库")
        logger.info("%s 历史回补 %s 至 %s，%s 个节点，%s 条", kind, first, last, len(chunk), len(rows))
        return query

    jobs = []
    for (first, last), nodes in sorted(batches.items()):
        nodes.sort()
        for offset in range(0, len(nodes), portwatch_downloads.BATCH_SIZE):
            chunk = tuple(nodes[offset:offset + portwatch_downloads.BATCH_SIZE])
            jobs.append((first, last, chunk))
    queries = []
    pool = ThreadPoolExecutor(max_workers=3)
    futures = {pool.submit(copy_context().run, download, *job): job for job in jobs}
    try:
        for future in as_completed(futures):
            first, last, chunk = futures[future]
            queries.append(future.result())
            for node in chunk:
                for day in _dates(first, last):
                    verified[node, day] = now
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    after = _state(kind, ids, end)
    report = _report(after, verified)
    if report["unverified_missing_records"]:
        raise ValueError(f"{kind} 仍有未校验的历史日期缺口")
    # Retain dated evidence only for actual source omissions; retry after 7 days.
    remaining = defaultdict(set)
    for node, day in after["missing"]:
        remaining[node, verified[node, day]].add(day)
    gaps = [{"node_id": node, "first": first.isoformat(), "last": last.isoformat(),
             "verified_at": checked.isoformat()}
            for (node, checked), days in sorted(remaining.items())
            for first, last in _intervals(days)]
    report.update({"node_ids": list(ids), "checked_at": now.isoformat(), "source_missing": gaps,
                   "repaired_records": len(state["missing"]) - len(after["missing"]),
                   "repair_queries": queries})
    data_store.set_meta(AUDIT_PREFIX + kind, report)
    return report


def validate_kind(kind, now=None):
    now = now or datetime.now(timezone.utc)
    state = _state(kind)
    report = _report(state, _verified_missing(state['audit'], now))
    if not state['audit'] or report['unverified_missing_records']:
        raise ValueError(f"{kind} 历史完整性校验失败：未校验缺口 {report['unverified_missing_records']} 条")
    return report


def validate_all(now=None):
    now = now or datetime.now(timezone.utc)
    reports = {}
    for kind in ("ports", "chokepoints"):
        reports[kind] = validate_kind(kind, now)
    return reports
