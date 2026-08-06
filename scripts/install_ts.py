"""Install the pinned Ts runtime into the active Python environment."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ts_runtime import (
    install_ts_runtime,
    load_pinned_metadata,
    materialize_git_runtime,
    smoke_test_runtime,
    temporary_work_directory,
)


def install(source_root: Path | None = None) -> Path:
    """Install a local Ts tree or download the pinned upstream commit."""

    metadata = load_pinned_metadata(PROJECT_ROOT)
    commit = metadata["commit"]
    if source_root is not None:
        candidate_root = source_root.resolve()
        smoke_test_runtime(candidate_root)
        return install_ts_runtime(candidate_root, commit=commit).root / "Ts"

    with temporary_work_directory(
        Path(tempfile.gettempdir()),
        prefix=f"{commit[:12]}-",
    ) as temporary:
        candidate_root = temporary / "candidate"
        materialize_git_runtime(commit, candidate_root)
        smoke_test_runtime(candidate_root)
        return install_ts_runtime(candidate_root, commit=commit).root / "Ts"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Root containing Ts/; intended for migrating a local source tree.",
    )
    options = parser.parse_args(arguments)
    installed_path = install(options.source_root)
    print(f"Ts installed at {installed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
