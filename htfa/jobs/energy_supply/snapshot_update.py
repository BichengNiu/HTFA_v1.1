"""Collect candidate facts with independent source rollback and validation."""

import json
import logging
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

import htfa.monitoring.energy_supply.data.storage as data_store
from htfa.monitoring.energy_supply.data.portwatch_client import request_budget
from htfa.monitoring.energy_supply.processing import catalogs


def inspect(path):
    with duckdb.connect(str(path), read_only=True) as conn:
        conn.execute("SET schema='energy_supply'")
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "portwatch_daily",
                "ais_reports",
                "sea_entries",
                "catalogs",
                "documents",
            )
        }
        latest = dict(
            conn.execute(
                "SELECT kind,MAX(day) FROM portwatch_daily GROUP BY kind"
            ).fetchall()
        )
        vessel = conn.execute("SELECT MAX(observed) FROM ais_reports").fetchone()[0]
        # Read/decode the tables used by the dashboard, not just their schema.
        conn.execute(
            "SELECT SUM(LENGTH(CAST(payload AS VARCHAR))) FROM catalogs"
        ).fetchone()
        conn.execute("SELECT COUNT(*) FROM asset_catalog").fetchone()
    return {"counts": counts, "latest_days": latest, "latest_vessel": vessel}


def validate_progress(before, after):
    for table in ("portwatch_daily", "sea_entries", "ais_reports"):
        if after["counts"][table] < before["counts"][table]:
            raise RuntimeError("历史记录减少，拒绝发布：" + table)
    for kind, day in before["latest_days"].items():
        if after["latest_days"].get(kind, day) < day:
            raise RuntimeError("来源数据日期倒退：" + kind)
    if before["latest_vessel"] and (
        not after["latest_vessel"] or after["latest_vessel"] < before["latest_vessel"]
    ):
        raise RuntimeError("船位日期倒退")


@contextmanager
def source_checkpoint(candidate):
    """Roll back every write by a failed source, including its catalog/meta."""
    with tempfile.TemporaryDirectory(
        prefix="source-checkpoint-", dir=candidate.parent
    ) as temporary:
        checkpoint = Path(temporary) / "before.duckdb"
        shutil.copy2(candidate, checkpoint)
        try:
            yield
        except Exception:
            Path(str(candidate) + ".wal").unlink(missing_ok=True)
            shutil.copy2(checkpoint, candidate)
            raise


def collect_candidate(
    original: Path,
    candidate: Path,
    *,
    force_ports=False,
    now=None,
    seed=None,
    retry_only=False,
):
    now = now or datetime.now(timezone.utc)
    before = inspect(original)
    shutil.copy2(seed or original, candidate)
    with data_store.job_database(candidate):
        import htfa.monitoring.energy_supply.processing.ais as ais
        import htfa.monitoring.energy_supply.processing.portwatch_history as portwatch_history
        from htfa.jobs.energy_supply import collector

        data_store.initialize()
        import htfa.monitoring.energy_supply.processing.pipeline_catalog as pipeline_catalog

        pipelines = pipeline_catalog.load()
        gas_connections = pipeline_catalog.load_gas_connections()
        unmapped_projects = pipeline_catalog.load_unmapped_projects()
        # Persist code-defined asset rules into the same candidate.
        import htfa.monitoring.energy_supply.processing.field_catalog as field_catalog

        catalogs.save_catalog("assets", field_catalog.build_catalog())
        from htfa.monitoring.energy_supply.processing.entity_names import (
            validate_catalogs,
        )

        # Enrich even when PortWatch is not due; identities and daily facts stay intact.
        for kind in ("assets", "ports", "chokepoints"):
            catalog = catalogs.load_catalog(kind)
            if kind == "ports":
                from htfa.monitoring.energy_supply.processing.port_additions import (
                    extend_inventory,
                )

                catalog = extend_inventory(catalog)
            catalogs.save_catalog(kind, catalog)
        validate_catalogs(
            {
                kind: catalogs.load_catalog(kind)
                for kind in ("assets", "ports", "chokepoints")
            }
        )
        from htfa.jobs.energy_supply.snapshot_retry import (
            SOURCES,
            decision,
            successful_sources,
        )

        previous = data_store.meta("published_snapshot", {})
        successes = successful_sources(previous, now)
        pending = set(decision(previous, now)["pending_sources"])
        source_results = {
            name: {
                "status": "skipped",
                "last_successful_collection": successes[name].isoformat()
                if name in successes
                else None,
            }
            for name in SOURCES
        }
        if not retry_only or "ais" in pending:
            try:
                with source_checkpoint(candidate):
                    source_before = inspect(candidate)
                    snapshot = collector.collect_once()
                    if (
                        snapshot.get("error")
                        or snapshot.get("archive_error")
                        or not snapshot.get("vessels")
                    ):
                        raise RuntimeError(
                            "船位采集未完整成功："
                            + str(
                                snapshot.get("archive_error") or snapshot.get("error")
                            )
                        )
                    observed = [
                        ais.parse_utc(row.get("observed_at"))
                        for row in snapshot["vessels"]
                    ]
                    if not any(
                        value
                        and now - timedelta(hours=2)
                        <= value
                        <= now + timedelta(minutes=5)
                        for value in observed
                    ):
                        raise RuntimeError("未取得最近两小时的有效船位")
                    validate_progress(source_before, inspect(candidate))
                source_results["ais"].update(
                    status="ok", last_successful_collection=now.isoformat()
                )
            except Exception as exc:
                source_results["ais"].update(
                    status="error", error=f"{type(exc).__name__}: {exc}"
                )
                logging.warning("船位更新失败，保留上次船位；继续港口更新：%s", exc)
        port_result = {"sources": {}}
        history_coverage = dict(previous.get("history_coverage", {}))
        for kind in ("ports", "chokepoints"):
            try:
                with source_checkpoint(candidate):
                    last_source = data_store.meta(
                        f"snapshot_portwatch_{kind}_completed_at",
                        data_store.meta("snapshot_portwatch_completed_at", ""),
                    )
                    history_due = portwatch_history.needs_repair(now, kind=kind)
                    due = (
                        force_ports
                        or history_due
                        or (
                            kind in pending
                            if retry_only
                            else not last_source
                            or datetime.fromisoformat(last_source).date() < now.date()
                        )
                    )
                    if due:
                        source_before = inspect(candidate)
                        with request_budget(3600 if history_due else 900):
                            result = collector.collect_portwatch_run(
                                strict=True, force=True, include_history=True, kind=kind
                            )
                        if result.get("status") != "ok":
                            raise RuntimeError("PortWatch未返回成功状态")
                        validate_catalogs(
                            {
                                name: catalogs.load_catalog(name)
                                for name in ("assets", "ports", "chokepoints")
                            }
                        )
                        coverage = portwatch_history.validate_kind(kind)
                        validate_progress(source_before, inspect(candidate))
                        data_store.set_meta(
                            f"snapshot_portwatch_{kind}_completed_at", now.isoformat()
                        )
                if due:
                    source_results[kind].update(
                        status="ok", last_successful_collection=now.isoformat()
                    )
                    history_coverage[kind] = coverage
                    port_result["sources"][kind] = result.get("sources", {}).get(
                        kind, {}
                    )
            except Exception as exc:
                source_results[kind].update(
                    status="error", error=f"{type(exc).__name__}: {exc}"
                )
                port_result["sources"][kind] = {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                logging.warning(
                    "%s更新失败，保留该类数据；不阻止其他数据发布：%s", kind, exc
                )
        port_result["status"] = (
            "partial"
            if any(
                source_results[k]["status"] == "error" for k in ("ports", "chokepoints")
            )
            else "ok"
        )
        if not (
            set(decision({"source_results": source_results}, now)["pending_sources"])
            & {"ports", "chokepoints"}
        ):
            data_store.set_meta(
                "snapshot_portwatch_completed_at",
                min(
                    source_results[k]["last_successful_collection"]
                    for k in ("ports", "chokepoints")
                ),
            )
        if not any(result["status"] == "ok" for result in source_results.values()):
            if any(result["status"] == "error" for result in source_results.values()):
                raise RuntimeError(
                    "本次没有数据源更新成功："
                    + json.dumps(source_results, ensure_ascii=False)
                )
        validate_catalogs(
            {
                kind: catalogs.load_catalog(kind)
                for kind in ("assets", "ports", "chokepoints")
            }
        )
        # Only expendable raw responses/caches expire. Facts and events accumulate.
        with data_store.connect() as conn:
            conn.execute(
                "DELETE FROM source_queries WHERE retrieved_at < ?",
                [now - timedelta(days=7)],
            )
            conn.execute(
                "DELETE FROM portwatch_cache WHERE saved < ?",
                [(now - timedelta(days=7)).timestamp()],
            )
        after = inspect(candidate)
        validate_progress(before, after)
        if not after["counts"]["catalogs"] or not after["counts"]["documents"]:
            raise RuntimeError("数据库目录或来源材料为空")
        summary = {
            "completed_at": now.isoformat(),
            "status": "partial"
            if any(r["status"] == "error" for r in source_results.values())
            else "ok",
            "source_results": source_results,
            "full_collection_complete": not decision(
                {"source_results": source_results}, now
            )["pending_sources"],
            "ais_updated": source_results["ais"]["status"] == "ok",
            "portwatch_updated": any(
                source_results[k]["status"] == "ok" for k in ("ports", "chokepoints")
            ),
            "ports_updated": source_results["ports"]["status"] == "ok",
            "chokepoints_updated": source_results["chokepoints"]["status"] == "ok",
            "pipelines": {
                "segments": len(pipelines["features"]),
                "drawable_segments": sum(
                    f["properties"].get("map_drawable", True)
                    for f in pipelines["features"]
                ),
                "gas_connection_records": len(gas_connections["features"]),
                "unmapped_projects": len(unmapped_projects),
                "source": pipelines["metadata"],
            },
            "portwatch": port_result,
            "history_coverage": history_coverage,
            "before": before,
            "after": after,
        }
        data_store.set_meta("published_snapshot", summary)
        # Every connection has closed: the file is checkpointed and portable.
        inspect(candidate)
        return summary
