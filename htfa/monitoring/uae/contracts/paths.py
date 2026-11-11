"""UAE 模块的数据资产位置；不执行 I/O。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ASSETS_RELATIVE_PATH = Path("htfa/monitoring/uae/assets")
ASSETS_DIR = PROJECT_ROOT / ASSETS_RELATIVE_PATH
