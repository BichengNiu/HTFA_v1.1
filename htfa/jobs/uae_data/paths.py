"""UAE 数据维护作业使用的项目与数据资产路径。"""

from __future__ import annotations

from pathlib import Path
import os


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[2]
DATA_DIR = Path(os.environ.get("HTFA_UAE_DATA_DIR", PROJECT_ROOT / "data" / "UAE")).resolve()
SCRIPTS_DIR = PACKAGE_DIR
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "uae.duckdb"
WORKBOOK_PATH = DATA_DIR / "阿联酋.xlsx"

__all__ = [
    "DATA_DIR",
    "DB_PATH",
    "PACKAGE_DIR",
    "PROJECT_ROOT",
    "RAW_DIR",
    "SCRIPTS_DIR",
    "WORKBOOK_PATH",
]
