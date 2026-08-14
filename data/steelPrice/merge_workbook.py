"""Safely invoke Excel to merge MEsteel data into data/阿联酋.xlsx."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
WORKBOOK_PATH = BASE_DIR.parent / "阿联酋.xlsx"
WIDE_PATH = BASE_DIR / "processed" / "mesteel_monthly_midpoint_wide.csv"
MERGE_SCRIPT = BASE_DIR / "merge_workbook.ps1"


def merge(
    workbook_path: Path = WORKBOOK_PATH,
    wide_path: Path = WIDE_PATH,
) -> Path:
    """Run the native Excel merge and return the updated workbook path."""
    workbook_path = workbook_path.resolve()
    wide_path = wide_path.resolve()
    lock_path = workbook_path.with_name(f"~${workbook_path.name}")
    if lock_path.exists():
        raise PermissionError(
            f"Close Excel before updating the workbook: {lock_path}"
        )
    for required in (workbook_path, wide_path, MERGE_SCRIPT):
        if not required.exists():
            raise FileNotFoundError(required)

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(MERGE_SCRIPT),
            "-WorkbookPath",
            str(workbook_path),
            "-WideCsvPath",
            str(wide_path),
        ],
        check=True,
        cwd=BASE_DIR,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("Excel merge did not complete successfully")
    return workbook_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        type=Path,
        default=WORKBOOK_PATH,
        help=f"Workbook path (default: {WORKBOOK_PATH})",
    )
    parser.add_argument(
        "--wide-csv",
        type=Path,
        default=WIDE_PATH,
        help=f"Cleaned wide CSV path (default: {WIDE_PATH})",
    )
    args = parser.parse_args()
    print(merge(args.workbook, args.wide_csv))


if __name__ == "__main__":
    main()
