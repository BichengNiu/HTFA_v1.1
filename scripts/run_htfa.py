"""Launch local HTFA with the newest validated Ts runtime available."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ts_runtime import (
    REQUIRED_INTERFACES,
    RuntimeSelection,
    RuntimeUpdateError,
    load_vendored_metadata,
    prepare_ts_runtime,
)


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
    missing = [
        name
        for name in REQUIRED_INTERFACES
        if not callable(getattr(module, name, None))
    ]
    if missing:
        raise RuntimeUpdateError(
            "selected Ts runtime is missing HTFA interfaces: " + ", ".join(missing)
        )
    return module


def activate_ts_runtime(
    selection: RuntimeSelection,
    *,
    project_root: Path = PROJECT_ROOT,
) -> tuple[ModuleType, RuntimeSelection]:
    """Preload the selected Ts package, falling back to the vendored copy."""

    _purge_ts_modules()
    try:
        return _load_ts_from(selection.root), selection
    except Exception as selected_error:  # noqa: BLE001 - imported code may fail freely
        _purge_ts_modules()
        _remove_path(selection.root)
        vendored_metadata = load_vendored_metadata(project_root)
        vendored = RuntimeSelection(
            root=project_root.resolve(),
            commit=vendored_metadata["commit"],
            source="vendored",
            detail=f"selected runtime failed to load: {selected_error}",
        )
        try:
            return _load_ts_from(vendored.root), vendored
        except Exception as vendored_error:
            raise RuntimeUpdateError(
                "both the selected and vendored Ts runtimes failed: "
                f"selected={selected_error}; vendored={vendored_error}"
            ) from vendored_error


def build_streamlit_argv(
    project_root: Path,
    extra_arguments: Sequence[str],
) -> list[str]:
    """Build deterministic Streamlit CLI arguments for the local launcher."""

    return [
        "streamlit",
        "run",
        str(project_root / "app.py"),
        "--server.headless",
        "false",
        *extra_arguments,
    ]


def format_selection_message(selection: RuntimeSelection) -> str:
    """Return a short Chinese status line for the startup console."""

    short_commit = selection.commit[:7]
    if selection.source == "downloaded":
        return f"[Ts] 已下载并使用最新版 {short_commit}"
    if selection.source == "cached":
        return f"[Ts] 使用最近验证版本 {short_commit}；{selection.detail}"
    return f"[Ts] 使用内置离线版本 {short_commit}；{selection.detail}"


def main(
    arguments: Sequence[str] | None = None,
    *,
    preparer: Callable[..., RuntimeSelection] | None = None,
    streamlit_main: Callable[[], int | None] | None = None,
) -> int:
    """Check Ts once, activate it, then start Streamlit in this process."""

    prepare = preparer or prepare_ts_runtime
    selected = prepare(project_root=PROJECT_ROOT)
    _, active = activate_ts_runtime(selected, project_root=PROJECT_ROOT)
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
