"""Merge DuckDB data back into the relevant ``data/UAE/阿联酋.xlsx`` sheets.

Each ``source_*.py`` module owns its sheet-writing protocol (Excel COM
helper, openpyxl direct write, or CSV export), exactly as the pre-DuckDB
scripts did, but reads its input from ``data/UAE/uae.duckdb``.

Close the workbook in Excel before merging; every writer keeps its backup
and rollback behaviour.

Examples::

    runtime\\python.exe -m htfa.jobs.uae_data.merge_workbook            # all sources
    runtime\\python.exe -m htfa.jobs.uae_data.merge_workbook --source cbuae
"""

from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from pathlib import Path

# 控制台默认按 GBK 输出，含中文/特殊字符的工作簿路径与错误详情会崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from .uae_metadata import sync_workbook_dictionary  # noqa: E402

WORKBOOK_PATH = DATA_DIR / "阿联酋.xlsx"

SOURCES = (
    "baker_hughes",
    "cbuae",
    "cloudflare_radar",
    "comtrade",
    "comtrade_vehicles",
    "ded",
    "dld",
    "employment",
    "emirates_post",
    "foreign_labour",
    "gfs",
    "pmi",
    "portwatch",
    "rta",
    "scad",
    "steel",
    "tdra",
    "uaewps",
    "extended",
    "wam",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="all",
        help="Comma-separated source names or 'all' (default).",
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=WORKBOOK_PATH,
        help=f"Destination workbook (default: {WORKBOOK_PATH}).",
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    names = resolve_source_names(args.source)
    workbook_path = args.workbook.resolve()
    print(f"[merge_workbook] sources: {', '.join(names)}", flush=True)
    failures = 0
    for name in names:
        try:
            module = importlib.import_module(f".source_{name}", package=__package__)
            outcome = module.merge(workbook_path)
            print(
                f"[merge_workbook] {name:<16} "
                f"{str(outcome.get('status', 'ok')):<8} "
                f"{outcome.get('note', '')}",
                flush=True,
            )
            if outcome.get("status") == "failed":
                failures += 1
        except Exception as exc:  # noqa: BLE001 - per-source isolation
            failures += 1
            detail = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip()
            print(f"[merge_workbook] {name:<16} FAILED  {detail}", flush=True)
    if failures == 0:
        try:
            dictionary = sync_workbook_dictionary(workbook_path)
            print(
                "[merge_workbook] metadata         ok       "
                f"added={dictionary['added']} updated={dictionary['updated']} "
                f"removed={dictionary['removed']} "
                f"sheet_indicators={dictionary['sheet_indicators']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - keep per-merge failure reporting
            failures += 1
            detail = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip()
            print(f"[merge_workbook] metadata         FAILED  {detail}", flush=True)
    print(
        f"[merge_workbook] done: {len(names) - failures} ok, {failures} failed; "
        f"workbook: {workbook_path}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
