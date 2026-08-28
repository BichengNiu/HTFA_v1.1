"""进程级 Streamlit 缓存的边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _cached_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if (
                isinstance(target, ast.Attribute)
                and target.attr in {"cache_data", "cache_resource"}
            ):
                names.add(node.name)
    return names


def test_workspace_does_not_use_process_wide_cache() -> None:
    root = PROJECT_ROOT / "dashboard" / "core" / "workspace"
    for path in root.rglob("*.py"):
        assert not _cached_functions(path), path


def test_only_fixed_weight_resource_uses_streamlit_process_cache() -> None:
    cached = {}
    for path in (PROJECT_ROOT / "dashboard").rglob("*.py"):
        functions = _cached_functions(path)
        if functions:
            cached[path.relative_to(PROJECT_ROOT).as_posix()] = functions

    assert cached == {
        "dashboard/analysis/industrial/utils/data_loader.py": {
            "load_weights_data"
        }
    }
