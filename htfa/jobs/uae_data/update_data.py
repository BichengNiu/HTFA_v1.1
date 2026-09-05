"""Unified fetch → clean → load pipeline for every ``data/`` source.

Runs each ``source_*.py`` module against the single ``data/UAE/uae.duckdb``
database.  One source failing never stops the others; the exit code only
reflects whether every requested source finished successfully.

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
from pathlib import Path

# 控制台默认按 GBK 输出，含中文/特殊字符的路径与错误详情会崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from .uae_metadata import complete_metadata  # noqa: E402

SOURCES = (
    "baker_hughes",
    "cbuae",
    "cloudflare_radar",
    "comtrade",
    "comtrade_vehicles",
    "ded",
    "dld",
    "dot_t100",
    "dubai_customs_air",
    "emirates_post",
    "employment",
    "eurostat_air",
    "foreign_labour",
    "gfs",
    "pmi",
    "portwatch",
    "rta",
    "salik",
    "scad",
    "steel",
    "tdra",
    "uaewps",
    "wam",
)


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


def resolve_source_names(specifier: str) -> list[str]:
    if specifier.strip().casefold() == "all":
        return list(SOURCES)
    names = [name.strip() for name in specifier.split(",") if name.strip()]
    unknown = [name for name in names if name not in SOURCES]
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(unknown)}")
    return names


def run_sources(
    source_names: list[str],
    *,
    force: bool = False,
    skip_download: bool = False,
) -> dict[str, dict]:
    """Run the named source modules and return one status record each."""

    con = db.connect()
    db.init_schema(con)

    results: dict[str, dict] = {}
    for name in source_names:
        started = datetime.now()
        try:
            module = importlib.import_module(f".source_{name}", package=__package__)
            outcome = module.update(
                con, force=force, skip_download=skip_download
            )
            outcome.setdefault("status", "ok")
            outcome.setdefault("rows", 0)
            outcome.setdefault("note", "")
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
    con.close()
    return results


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
        outcome = results.get(name, {"status": "failed", "note": "no result"})
        marker = {"ok": "OK", "skipped": "SKIP", "failed": "FAIL"}.get(
            outcome["status"], "FAIL"
        )
        print(
            f"[update_data] {name:<16} {marker:<4} "
            f"rows={outcome.get('rows', 0):>8}  {outcome.get('note', '')}",
            flush=True,
        )
        if outcome["status"] != "ok":
            failures += 1
    metadata_outcome = results.get("_metadata")
    if metadata_outcome is not None:
        print(
            f"[update_data] {'metadata':<16} "
            f"{'OK' if metadata_outcome['status'] == 'ok' else 'FAIL':<4} "
            f"rows={metadata_outcome.get('rows', 0):>8}  "
            f"{metadata_outcome.get('note', '')}",
            flush=True,
        )
        if metadata_outcome["status"] != "ok":
            failures += 1
    print(
        f"[update_data] done: {len(names) - failures} ok, {failures} failed; "
        f"database: {db.DB_PATH}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
