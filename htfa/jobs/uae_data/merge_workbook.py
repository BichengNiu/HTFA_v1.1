"""Merge DuckDB data back into the relevant ``data/UAE/阿联酋.xlsx`` sheets.

Each ``source_*.py`` module owns its workbook sheets and reads their values
from ``data/UAE/uae.duckdb``. Writers use Excel COM or atomic OOXML writes.

Close the workbook in Excel before merging; every writer keeps its backup
and rollback behaviour.

Examples::

    htfa\\jobs\\uae_data\\merge_workbook.bat            # all sources
    htfa\\jobs\\uae_data\\merge_workbook.bat --source cbuae
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import traceback
from pathlib import Path

# 控制台默认按 GBK 输出，含中文/特殊字符的工作簿路径与错误详情会崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .source_registry import resolve_source_names
from .paths import DATA_DIR
from ._excel_helpers import cleanup_excel_automation


from .uae_metadata import sync_workbook_dictionary  # noqa: E402
from . import db
from .publish_report import publish_workbook

WORKBOOK_PATH = DATA_DIR / "阿联酋.xlsx"


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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    names = resolve_source_names(args.source)
    workbook_path = args.workbook.resolve()
    print(f"[merge_workbook] sources: {', '.join(names)}", flush=True)
    failures = 0
    for name in names:
        # A COM helper may outlive its PowerShell process by a short interval.
        # Clean that state before and after every source so the next writer or
        # an OOXML atomic replace never races a stale hidden Excel lock.
        if os.name == "nt":
            cleanup_excel_automation()
        try:
            module = importlib.import_module(f".source_{name}", package=__package__)
            outcome = module.merge(workbook_path)
            if outcome.get("status") not in {"ok", "skipped"}:
                raise ValueError(f"合并未报告成功：{outcome.get('status')!r}")
            print(
                f"[merge_workbook] {name:<16} "
                f"{outcome['status']:<8} "
                f"{outcome.get('note', '')}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - per-source isolation
            failures += 1
            detail = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip()
            print(f"[merge_workbook] {name:<16} FAILED  {detail}", flush=True)
        finally:
            if os.name == "nt":
                cleanup_excel_automation()
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
    if failures == 0:
        try:
            with db.connect() as con:
                publication = publish_workbook(con, workbook_path)
            print(
                "[merge_workbook] report           ok       "
                f"{publication['sheets']} tables, "
                f"{publication['observations']} observations; "
                f"version={publication['version'][:12]}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - preserve previous publication
            failures += 1
            print(f"[merge_workbook] report           FAILED  {exc}", flush=True)
    print(
        f"[merge_workbook] done: {len(names) - failures} ok, {failures} failed; "
        f"workbook: {workbook_path}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
