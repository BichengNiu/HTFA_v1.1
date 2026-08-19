"""Update Ts once and launch HTFA in the current Python process.

Data updates no longer run at startup: the DuckDB pipeline under ``data/``
is triggered explicitly via ``data/UAE/scripts/update_data.bat`` / ``merge_workbook.bat``.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ts_runtime import RuntimeSelection, RuntimeUpdateError, prepare_ts_runtime


def _purge_ts_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "Ts" or module_name.startswith("Ts."):
            del sys.modules[module_name]


def _remove_path(path: Path) -> None:
    expected = str(path.resolve())
    sys.path[:] = [
        entry
        for entry in sys.path
        if str(Path(entry or ".").resolve()) != expected
    ]


def _load_ts_from(root: Path) -> ModuleType:
    root = root.resolve()
    _remove_path(root)
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    module = importlib.import_module("Ts")
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        raise RuntimeUpdateError("selected Ts module has no source path")
    actual_root = Path(module_file).resolve().parent
    expected_root = (root / "Ts").resolve()
    if actual_root != expected_root:
        raise RuntimeUpdateError(
            f"selected Ts path mismatch: expected {expected_root}, got {actual_root}"
        )
    return module


def activate_ts_runtime(
    selection: RuntimeSelection,
) -> tuple[ModuleType, RuntimeSelection]:
    """Import the selected Ts without interface checks or fallback."""

    _purge_ts_modules()
    return _load_ts_from(selection.root), selection


def build_streamlit_argv(
    project_root: Path,
    extra_arguments: Sequence[str],
) -> list[str]:
    """Build deterministic Streamlit CLI arguments."""

    return [
        "streamlit",
        "run",
        str(project_root / "app.py"),
        "--server.headless",
        "false",
        *extra_arguments,
    ]


def format_selection_message(selection: RuntimeSelection) -> str:
    short_commit = selection.commit[:7]
    if selection.source == "downloaded":
        return f"[Ts] Updated from main: {short_commit}"
    return f"[Ts] Using local version {short_commit}: {selection.detail}"


def main(
    arguments: Sequence[str] | None = None,
    *,
    preparer: Callable[..., RuntimeSelection] | None = None,
    streamlit_main: Callable[[], int | None] | None = None,
) -> int:
    """Check Ts once, then start Streamlit.

    Data refreshes are no longer performed here; run ``data/UAE/scripts/update_data.py``
    and ``data/UAE/scripts/merge_workbook.py`` explicitly when new data is available.
    """

    prepare = preparer or prepare_ts_runtime
    selected = prepare(project_root=PROJECT_ROOT)
    _, active = activate_ts_runtime(selected)
    print(format_selection_message(active), flush=True)

    sys.argv = build_streamlit_argv(PROJECT_ROOT, list(arguments or ()))
    if streamlit_main is None:
        from streamlit.web.cli import main as streamlit_cli_main

        streamlit_main = streamlit_cli_main
    result = streamlit_main()
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = [
    "activate_ts_runtime",
    "build_streamlit_argv",
    "format_selection_message",
    "main",
]
