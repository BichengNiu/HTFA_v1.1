"""Build the self-contained Windows x64 HTFA project runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import subprocess
import sys
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.install_ts import install as install_ts
from scripts.ts_runtime import load_pinned_metadata
SPEC_PATH = PROJECT_ROOT / "scripts" / "portable_runtime.json"
LOCK_PATH = PROJECT_ROOT / "requirements-win-py313.lock"
BUILD_ROOT = PROJECT_ROOT / "build" / "portable"
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
USER_AGENT = "HTFA portable builder"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_portable_spec(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    """Load and validate the pinned official Python runtime specification."""

    path = project_root / "scripts" / "portable_runtime.json"
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid portable runtime specification: {exc}") from exc
    required = {"python_version", "platform", "archive_url", "archive_sha256"}
    if set(spec) != required:
        raise ValueError("portable runtime specification fields are invalid")
    if spec["python_version"] != "3.13.4" or spec["platform"] != "win_amd64":
        raise ValueError("portable runtime must be CPython 3.13.4 win_amd64")
    digest = str(spec["archive_sha256"])
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("portable runtime SHA-256 is invalid")
    return {key: str(value) for key, value in spec.items()}


def assert_safe_generated_target(
    project_root: Path,
    target: Path,
    expected: Path,
) -> Path:
    """Return a generated target only when it is the exact approved child path."""

    project_root = project_root.resolve()
    target = target.resolve()
    expected = expected.resolve()
    try:
        target.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"unsafe generated target outside project: {target}") from exc
    if target == project_root or target != expected:
        raise ValueError(f"unsafe generated target: {target}")
    return target


def _remove_readonly(
    function: Callable[[str], Any],
    path: str,
    error: BaseException,
) -> None:
    if not isinstance(error, PermissionError):
        raise error
    Path(path).chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    function(path)


def _reset_generated_directory(
    project_root: Path,
    target: Path,
    expected: Path,
) -> Path:
    target = assert_safe_generated_target(project_root, target, expected)
    if target.exists():
        shutil.rmtree(target, onexc=_remove_readonly)
    target.mkdir(parents=True)
    return target


def write_embedded_path_file(runtime_root: Path) -> Path:
    """Enable the standard library and bundled site-packages in embedded Python."""

    path_file = runtime_root / "python313._pth"
    path_file.write_text(
        "python313.zip\n.\nLib\nLib/site-packages\nimport site\n",
        encoding="utf-8",
    )
    return path_file



def build_manifest(
    spec: dict[str, str],
    lock_path: Path,
    *,
    ts_commit: str,
    built_at: str | None = None,
) -> dict[str, Any]:
    """Build the machine-readable release manifest."""

    return {
        "python": dict(spec),
        "dependency_lock": {
            "file": lock_path.name,
            "sha256": _sha256_file(lock_path),
        },
        "ts_commit": ts_commit,
        "built_at": built_at or datetime.now(timezone.utc).isoformat(),
    }


def _download_file(
    url: str,
    destination: Path,
    *,
    opener: Callable[..., Any] = urlopen,
) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=60) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _extract_python_archive(archive_path: Path, runtime_root: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(runtime_root)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"invalid official Python archive: {exc}") from exc


def _run_checked(arguments: list[str], *, cwd: Path) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


def install_locked_dependencies(
    builder_python: Path,
    runtime_python: Path,
    lock_path: Path,
    *,
    cwd: Path,
) -> None:
    """Use builder pip to install exact binary wheels into embedded Python."""

    _run_checked(
        [
            str(builder_python),
            "-m",
            "pip",
            "--python",
            str(runtime_python),
            "install",
            "--only-binary=:all:",
            "--no-deps",
            "--no-cache-dir",
            "--no-compile",
            "--requirement",
            str(lock_path),
        ],
        cwd=cwd,
    )


def remove_console_scripts(runtime_root: Path) -> None:
    """Remove generated entry points that embed the build-machine path."""

    scripts_root = runtime_root / "Scripts"
    if scripts_root.exists():
        shutil.rmtree(scripts_root, onexc=_remove_readonly)


def verify_runtime(runtime_python: Path, *, project_root: Path) -> None:
    imports = (
        "streamlit, pandas, numpy, scipy, statsmodels, sklearn, matplotlib, "
        "dtaidistance, arch, Ts"
    )
    _run_checked(
        [
            str(runtime_python),
            "-B",
            "-c",
            f"import {imports}; print('portable runtime imports OK')",
        ],
        cwd=project_root,
    )


def build(
    *,
    project_root: Path = PROJECT_ROOT,
    builder_python: Path = Path(sys.executable),
    opener: Callable[..., Any] = urlopen,
) -> Path:
    """Build and verify the project-root runtime directory."""

    project_root = project_root.resolve()
    spec = load_portable_spec(project_root)
    lock_path = project_root / "requirements-win-py313.lock"
    build_root = _reset_generated_directory(
        project_root,
        project_root / "build" / "portable",
        project_root / "build" / "portable",
    )
    runtime_root = _reset_generated_directory(
        project_root,
        project_root / "runtime",
        project_root / "runtime",
    )

    archive_path = build_root / "python-3.13.4-embed-amd64.zip"
    _download_file(spec["archive_url"], archive_path, opener=opener)
    actual_digest = _sha256_file(archive_path)
    if actual_digest != spec["archive_sha256"]:
        raise RuntimeError(
            "official Python archive SHA-256 mismatch: "
            f"expected {spec['archive_sha256']}, got {actual_digest}"
        )
    _extract_python_archive(archive_path, runtime_root)
    write_embedded_path_file(runtime_root)
    site_packages = runtime_root / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    runtime_python = runtime_root / "python.exe"

    install_locked_dependencies(
        builder_python.resolve(),
        runtime_python,
        lock_path,
        cwd=project_root,
    )
    remove_console_scripts(runtime_root)

    pinned = load_pinned_metadata(project_root)
    install_ts(install_root=site_packages)
    manifest = build_manifest(
        spec,
        lock_path,
        ts_commit=pinned["commit"],
    )
    (runtime_root / "runtime-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verify_runtime(runtime_python, project_root=project_root)
    return runtime_root


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args(arguments)
    runtime_root = build()
    print(f"Portable HTFA runtime built at {runtime_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
