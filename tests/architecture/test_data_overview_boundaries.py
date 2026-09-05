"""运行时导入边界回归测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_fresh_process(source: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    bootstrap = f"import sys\nsys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
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
from htfa.data.tabular import build_overview_dataset
from htfa.data.file_content import file_fingerprint

assert callable(build_overview_dataset)
assert callable(file_fingerprint)
assert not any(
    name == "streamlit" or name.startswith("streamlit.")
    for name in sys.modules
)
assert not any(
    name == "htfa.workspace"
    or name.startswith("htfa.workspace.")
    for name in sys.modules
)
assert not any(
    name == "htfa.data.economic_workbook"
    or name.startswith("htfa.data.economic_workbook.")
    for name in sys.modules
)
"""
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_ui_package_loads_streamlit_only_at_the_ui_boundary() -> None:
    result = _run_fresh_process(
        """
from htfa.ui_shared.data_overview import create_data_overview

assert callable(create_data_overview)
assert "streamlit" in sys.modules
assert "htfa.ui_shared.data_overview.ui" in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_removed_data_overview_import_paths_are_not_resolvable() -> None:
    result = _run_fresh_process(
        """
import importlib
import importlib.util

for name in ("components.data_overview", "data_overview"):
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError as exc:
        assert exc.name in {name, name.split(".", 1)[0]}, exc
        spec = None
    assert spec is None, f"旧入口仍可解析：{name} -> {spec}"
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as exc:
        assert exc.name in {name, name.split(".", 1)[0]}, exc
    else:
        raise AssertionError(f"旧入口仍可导入：{name}")
"""
    )

    assert result.returncode == 0, result.stderr or result.stdout
