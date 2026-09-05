"""运行时导入边界回归测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMPONENTS_ROOT = PROJECT_ROOT / "components"


def _run_fresh_process(source: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    bootstrap = f"import sys\nsys.path.insert(0, {str(COMPONENTS_ROOT)!r})\n"
    return subprocess.run(
        [sys.executable, "-c", bootstrap + source],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_pure_file_parsing_import_does_not_load_ui_or_streamlit() -> None:
    result = _run_fresh_process(
        """
from data_overview import build_overview_dataset
from data_overview.core.file_parsing import file_fingerprint

assert callable(build_overview_dataset)
assert callable(file_fingerprint)
assert not any(
    name == "streamlit" or name.startswith("streamlit.")
    for name in sys.modules
)
assert not any(
    name == "data_overview.ui" or name.startswith("data_overview.ui.")
    for name in sys.modules
)
assert not any(
    name == "htfa.workspace"
    or name.startswith("htfa.workspace.")
    for name in sys.modules
)
"""
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_ui_exports_are_loaded_on_demand_without_breaking_public_api() -> None:
    result = _run_fresh_process(
        """
from data_overview import create_data_overview

assert callable(create_data_overview)
assert "streamlit" in sys.modules
assert "data_overview.ui" in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr or result.stdout
