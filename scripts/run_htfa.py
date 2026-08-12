"""Update Ts once and launch HTFA in the current Python process."""

from __future__ import annotations

import importlib
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ts_runtime import RuntimeSelection, RuntimeUpdateError, prepare_ts_runtime


class DataRefreshError(RuntimeError):
    """Raised when a managed source workbook cannot be refreshed."""


def refresh_baker_hughes_data(
    project_root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> bool:
    """Refresh the UAE Baker Hughes sheet before launch on Windows."""

    if sys.platform != "win32":
        return False
    updater = (
        project_root
        / "scripts"
        / "data_sources"
        / "baker_hughes"
        / "update_baker_hughes_monthly.py"
    )
    if not updater.is_file():
        return False
    run = runner or subprocess.run
    completed = run(
        [sys.executable, str(updater)],
        cwd=project_root,
        check=False,
        text=True,
    )
    if completed.returncode:
        raise DataRefreshError(
            "Baker Hughes monthly-data refresh failed with exit code "
            f"{completed.returncode}"
        )
    return True


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
    data_refresher: Callable[[Path], bool] | None = None,
    streamlit_main: Callable[[], int | None] | None = None,
) -> int:
    """Refresh managed data, check Ts once, then start Streamlit."""

    refresh_data = data_refresher or refresh_baker_hughes_data
    refresh_data(PROJECT_ROOT)
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
    "DataRefreshError",
    "activate_ts_runtime",
    "build_streamlit_argv",
    "format_selection_message",
    "main",
    "refresh_baker_hughes_data",
]
