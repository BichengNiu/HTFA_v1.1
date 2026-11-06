"""Source collectors invoked exclusively by the HTFA publication job."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

from htfa.monitoring.energy_supply import ais
from htfa.monitoring.energy_supply import ais_history
from htfa.monitoring.energy_supply import data_store
from htfa.monitoring.energy_supply import sea_tracking

logger = logging.getLogger(__name__)


def collect_once():
    sea_tracking.start_collection()
    started = datetime.now(timezone.utc)
    details, rows, inserted, snapshot = {}, [], 0, None
    status = "error"
    try:
        snapshot = ais.openwaters_snapshot(max_age_minutes=120)
        rejected = 0
        for row in snapshot.get("reports", snapshot.get("vessels", [])):
            try:
                rows.append(ais_history.normalize_report(row))
            except ValueError:
                rejected += 1
        inserted = ais_history.archive_reports(rows)
        details = {"source_error": snapshot.get("error"), "truncated": snapshot.get("truncated"),
                   "requested_groups": snapshot.get("requested_groups"),
                   "successful_groups": snapshot.get("successful_groups"),
                   "rejected_reports": rejected, "inserted_reports": inserted,
                   "attribution": snapshot.get("attribution"), "coverage": "observed AIS sample"}
        status = "ok" if not snapshot.get("error") and not snapshot.get("truncated") and not rejected else "partial"
    except Exception as exc:
        details["error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("AIS collection failed: %s", type(exc).__name__)
    finished = datetime.now(timezone.utc)
    with data_store.connect() as conn:
        conn.execute("INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?)",
                     (uuid.uuid4().hex, "Open Waters", started, finished, status, len(rows), data_store.encode(details)))
        if not inserted:
            data_store.bump_revision("sea", conn)
    snapshot = snapshot or {"vessels": [], "error": details.get("error"), "fetched_at": finished.isoformat()}
    if status != "ok":
        snapshot["archive_error"] = details.get("error") or details.get("source_error") or "上游截断或报告未通过校验"
    else:
        snapshot["archive_error"] = None
    # The map receives only the latest display positions, not an archive-sized payload.
    snapshot.pop("reports", None)
    snapshot["refresh_summary"] = {
        "fetched": len(rows),
        "inserted": inserted,
        "rejected": details.get("rejected_reports", 0),
        "truncated": bool(details.get("truncated")),
    }
    return snapshot


def collect_portwatch(*, force=False, include_history=False, kind=None):
    """Archive latest validated daily facts, with source-dated backfill windows."""
    from htfa.monitoring.energy_supply import portwatch
    from htfa.monitoring.energy_supply import portwatch_downloads
    revision = uuid.uuid4().hex
    summaries = {}
    if kind not in (None, 'ports', 'chokepoints'):
        raise ValueError('未知的PortWatch数据类型')
    selected_kind = kind
    for kind, catalog_reader, latest_reader in (
        ("ports", portwatch.port_catalog, portwatch.latest_date),
        ("chokepoints", portwatch.chokepoint_catalog, portwatch.latest_chokepoint_date),
    ):
        if selected_kind is not None and kind != selected_kind:
            continue
        catalog = catalog_reader(revision)
        ids = tuple(sorted(str(row["portid"]) for row in catalog
                           if kind == "chokepoints" or portwatch.has_independent_statistics(row)))
        end = latest_reader(revision)
        from datetime import timedelta
        if not ids or end is None:
            raise ValueError(f"{kind} 上游目录或日期为空")
        periods = [(end - timedelta(days=13), end, force)]
        total = 0
        for first, last, refresh in periods:
            for offset in range(0, len(ids), portwatch_downloads.BATCH_SIZE):
                rows, _ = portwatch_downloads.fetch_window(
                    kind, ids[offset:offset + portwatch_downloads.BATCH_SIZE], first, last,
                    force=refresh, cache_ttl_seconds=365 * 86400 if not refresh else 86400,
                )
                total += len(rows)
                if refresh and not rows:
                    raise ValueError(f"{kind} 最新窗口未返回记录")
        summaries[kind] = {"latest_day": end.isoformat(), "queried_rows": total}
        if include_history:
            from htfa.monitoring.energy_supply import portwatch_history
            summaries[kind]["history"] = portwatch_history.repair(kind, ids, end)
        if include_history and kind == "ports":
            try:
                # The secondary risk model must leave time for the remaining
                # daily facts, even while transport fallbacks are retrying.
                with portwatch.request_budget(20):
                    values = portwatch.port_risk_capacity(ids, revision)
                data_store.set_meta("port_risk_capacity_snapshot", {
                    "port_ids": ids, "values": values,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as exc:
                # A secondary model must not discard validated daily facts.
                summaries[kind]["risk_error"] = f"{type(exc).__name__}: {exc}"
    return summaries


def collect_portwatch_run(*, strict=False, force=False, include_history=False, kind=None):
    started = datetime.now(timezone.utc)
    status, details = "ok", {}
    try:
        details["sources"] = collect_portwatch(force=force, include_history=include_history, kind=kind)
    except Exception as exc:
        status = "error"
        details["error"] = str(exc)
        logger.warning("PortWatch collection failed: %s", type(exc).__name__)
    with data_store.connect() as conn:
        conn.execute("INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?)",
                     (uuid.uuid4().hex, "PortWatch", started, datetime.now(timezone.utc), status, 0, data_store.encode(details)))
    if strict and status != "ok":
        raise RuntimeError(details["error"])
    return {"status": status, **details}
