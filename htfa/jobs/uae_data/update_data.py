"""Unified fetch → clean → load pipeline for every ``data/`` source.

Runs each ``source_*.py`` module against the single ``data/UAE/uae.duckdb``
database, then merges the requested sources from DuckDB into the workbook.
All requested source updates run so the command reports every failure. Any
update failure stops the workbook merge, preventing old DuckDB rows from being
written back as if they were freshly downloaded.

Examples::

    htfa\\jobs\\uae_data\\update_data.bat                 # all sources
    htfa\\jobs\\uae_data\\update_data.bat --source cbuae,gfs
    htfa\\jobs\\uae_data\\update_data.bat --skip-download  # reuse raw files
    htfa\\jobs\\uae_data\\update_data.bat --force
"""

from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from datetime import datetime

# 控制台默认按 GBK 输出，含中文/特殊字符的路径与错误详情会崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .source_registry import SOURCES, resolve_source_names
from . import db  # noqa: E402
from .uae_metadata import complete_metadata  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="all",
        help="Comma-separated source names or 'all' (default). "
        f"Available: {', '.join(SOURCES)}.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Do not fetch from the network; parse and load from data/UAE/raw/ only.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download cached inputs even when they look current.",
    )
    return parser.parse_args(argv)


def run_sources(
    source_names: list[str],
    *,
    force: bool = False,
    skip_download: bool = False,
) -> dict[str, dict]:
    """Run the named source modules and return one status record each."""

    con = db.connect()
    try:
        db.init_schema(con)

        results: dict[str, dict] = {}
        for name in source_names:
            started = datetime.now()
            try:
                module = importlib.import_module(f".source_{name}", package=__package__)
                outcome = module.update(
                    con, force=force, skip_download=skip_download
                )
                if outcome.get("status") != "ok":
                    raise ValueError(f"数据源未报告成功：{outcome.get('status')!r}")
                results[name] = outcome
                db.log_run(
                    con,
                    name,
                    str(outcome["status"]),
                    started_at=started,
                    note=str(outcome.get("note", "")),
                )
            except Exception as exc:  # noqa: BLE001 - per-source isolation
                detail = "".join(
                    traceback.format_exception_only(type(exc), exc)
                ).strip()
                results[name] = {
                    "status": "failed",
                    "rows": 0,
                    "note": detail,
                }
                db.log_run(
                    con,
                    name,
                    "failed",
                    started_at=started,
                    note=detail,
                )
        metadata_started = datetime.now()
        try:
            metadata = complete_metadata(con)
            results["_metadata"] = {
                "status": "ok",
                "rows": metadata["indicator_rows"] + metadata["column_rows"],
                "note": (
                    f"指标 {metadata['indicator_rows']} 行、字段 "
                    f"{metadata['column_rows']} 行已补齐"
                ),
            }
            db.log_run(
                con,
                "metadata",
                "ok",
                started_at=metadata_started,
                note=results["_metadata"]["note"],
            )
        except Exception as exc:  # noqa: BLE001 - metadata is part of the pipeline contract
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            results["_metadata"] = {"status": "failed", "rows": 0, "note": detail}
            db.log_run(con, "metadata", "failed", started_at=metadata_started, note=detail)
        return results
    finally:
        con.close()


def workbook_merge_sources(source_names: list[str]) -> list[str]:
    """Map update-source names to the corresponding workbook merge modules."""

    requested = set(source_names)
    return [name for name in SOURCES if name in requested]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    names = resolve_source_names(args.source)
    print(f"[update_data] sources: {', '.join(names)}", flush=True)
    results = run_sources(
        names,
        force=args.force,
        skip_download=args.skip_download,
    )
    failures = 0
    for name in names:
        outcome = results[name]
        marker = "OK" if outcome["status"] == "ok" else "FAIL"
        print(
            f"[update_data] {name:<16} {marker:<4} "
            f"rows={outcome.get('rows', 0):>8}  {outcome.get('note', '')}",
            flush=True,
        )
        if outcome["status"] != "ok":
            failures += 1
    metadata_outcome = results["_metadata"]
    print(
        f"[update_data] {'metadata':<16} "
        f"{'OK' if metadata_outcome['status'] == 'ok' else 'FAIL':<4} "
        f"rows={metadata_outcome.get('rows', 0):>8}  "
        f"{metadata_outcome.get('note', '')}",
        flush=True,
    )
    if metadata_outcome["status"] != "ok":
        failures += 1

    if failures:
        total_steps = len(names) + 1
        print(
            f"[update_data] stopped before workbook merge: "
            f"{total_steps - failures} ok, {failures} failed; database: {db.DB_PATH}",
            flush=True,
        )
        raise RuntimeError(
            f"UAE data refresh failed in {failures} step(s); workbook merge was skipped."
        )

    merge_names = workbook_merge_sources(names)
    print(f"[update_data] workbook merge: {', '.join(merge_names)}", flush=True)
    merge_detail = ""
    try:
        merge_module = importlib.import_module(".merge_workbook", package=__package__)
        merge_status = merge_module.main(["--source", ",".join(merge_names)])
    except Exception as exc:  # noqa: BLE001 - report final workbook stage
        merge_detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        merge_status = 1
    if merge_status:
        failures += 1
        suffix = f" {merge_detail}" if merge_detail else ""
        print(f"[update_data] workbook_merge   FAIL{suffix}", flush=True)
    else:
        print("[update_data] workbook_merge   OK", flush=True)

    total_steps = len(names) + 2
    print(
        f"[update_data] done: {total_steps - failures} ok, {failures} failed; "
        f"database: {db.DB_PATH}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
