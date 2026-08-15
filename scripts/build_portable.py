"""Finalize and verify the self-contained HTFA candidate runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import subprocess
import sys
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.install_ts import install as install_ts
from scripts.ts_runtime import load_pinned_metadata, sha256_file

CANDIDATE_ROOT = PROJECT_ROOT / "build" / "runtime-candidate"


def load_portable_spec(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    """Load and validate the pinned Python and pip bootstrap specification."""

    path = project_root / "scripts" / "portable_runtime.json"
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid portable runtime specification: {exc}") from exc
    required = {
        "python_version",
        "platform",
        "archive_url",
        "archive_sha256",
        "pip_version",
        "pip_wheel_url",
        "pip_wheel_sha256",
    }
    if set(spec) != required:
        raise ValueError("portable runtime specification fields are invalid")
    if spec["python_version"] != "3.13.4" or spec["platform"] != "win_amd64":
        raise ValueError("portable runtime must be CPython 3.13.4 win_amd64")
    if spec["pip_version"] != "26.1.2":
        raise ValueError("portable runtime must use pip 26.1.2")
    for field in ("archive_sha256", "pip_wheel_sha256"):
        digest = str(spec[field])
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError(f"portable runtime {field} is invalid")
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


def assert_safe_bootstrap_wheel(
    project_root: Path,
    wheel_path: Path,
    *,
    pip_version: str,
) -> Path:
    """Validate the exact generated location and name of the pip wheel."""

    expected = (
        project_root.resolve()
        / "build"
        / "portable"
        / f"pip-{pip_version}-py3-none-any.whl"
    )
    wheel_path = wheel_path.resolve()
    if wheel_path != expected:
        raise ValueError(f"unsafe pip bootstrap wheel: {wheel_path}")
    return wheel_path


def _remove_readonly(
    function: Callable[[str], Any],
    path: str,
    error: BaseException,
) -> None:
    if not isinstance(error, PermissionError):
        raise error
    Path(path).chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    function(path)


def write_embedded_path_file(runtime_root: Path) -> Path:
    """Enable the standard library and bundled site-packages."""

    path_file = runtime_root / "python313._pth"
    path_file.write_text(
        "python313.zip\n.\nLib\nLib/site-packages\nimport site\n",
        encoding="utf-8",
    )
    return path_file


def write_runtime_isolation(site_packages: Path) -> Path:
    """Prevent the portable runtime from importing per-user packages."""

    site_packages.mkdir(parents=True, exist_ok=True)
    sitecustomize = site_packages / "sitecustomize.py"
    sitecustomize.write_text(
        '"""Keep the HTFA runtime isolated from per-user site-packages."""\n'
        "import os\n"
        "import site\n"
        "import sys\n\n"
        "_user_sites = site.getusersitepackages()\n"
        "if isinstance(_user_sites, str):\n"
        "    _user_sites = (_user_sites,)\n"
        "_normalized_user_sites = {\n"
        "    os.path.normcase(os.path.abspath(path)) for path in _user_sites\n"
        "}\n"
        "sys.path[:] = [\n"
        "    path for path in sys.path\n"
        "    if os.path.normcase(os.path.abspath(path)) "
        "not in _normalized_user_sites\n"
        "]\n"
        "site.ENABLE_USER_SITE = False\n",
        encoding="utf-8",
    )
    return sitecustomize


def write_project_root_path(site_packages: Path, project_root: Path) -> Path:
    """Expose the local project packages to the machine-local runtime."""

    site_packages.mkdir(parents=True, exist_ok=True)
    path_file = site_packages / "htfa-project-root.pth"
    path_file.write_text(f"{project_root.resolve()}\n", encoding="utf-8")
    return path_file


def build_manifest(
    spec: dict[str, str],
    lock_path: Path,
    *,
    ts_commit: str,
    built_at: str | None = None,
) -> dict[str, Any]:
    """Build the machine-readable unified-runtime manifest."""

    python_spec = {
        key: value for key, value in spec.items() if not key.startswith("pip_")
    }
    return {
        "python": python_spec,
        "pip": {
            "version": spec["pip_version"],
            "wheel_sha256": spec["pip_wheel_sha256"],
        },
        "dependency_lock": {
            "file": lock_path.name,
            "sha256": sha256_file(lock_path),
        },
        "ts_commit": ts_commit,
        "built_at": built_at or datetime.now(timezone.utc).isoformat(),
    }


def _run_checked(arguments: list[str], *, cwd: Path) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


def install_pip_bootstrap(pip_wheel: Path, site_packages: Path) -> None:
    """Safely unpack the hash-verified pip wheel into the candidate runtime."""

    site_packages.mkdir(parents=True, exist_ok=True)
    destination_root = site_packages.resolve()
    with zipfile.ZipFile(pip_wheel) as archive:
        validated_members: list[tuple[zipfile.ZipInfo, Path]] = []
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            destination = destination_root.joinpath(*relative.parts).resolve()
            try:
                destination.relative_to(destination_root)
            except ValueError as exc:
                raise ValueError(
                    f"unsafe path in pip wheel: {member.filename}"
                ) from exc
            unix_mode = member.external_attr >> 16
            if relative.is_absolute() or ".." in relative.parts or stat.S_ISLNK(unix_mode):
                raise ValueError(f"unsafe path in pip wheel: {member.filename}")
            validated_members.append((member, destination))

        for member, destination in validated_members:
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def install_locked_dependencies(
    runtime_python: Path,
    lock_path: Path,
    *,
    cwd: Path,
) -> None:
    """Install the exact lock through the candidate runtime's own pip."""

    _run_checked(
        [
            str(runtime_python),
            "-I",
            "-B",
            "-m",
            "pip",
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
    """Remove entry points that contain the temporary candidate path."""

    scripts_root = runtime_root / "Scripts"
    if scripts_root.exists():
        shutil.rmtree(scripts_root, onexc=_remove_readonly)


def verify_runtime(runtime_python: Path, *, project_root: Path) -> None:
    """Verify imports and dependency consistency."""

    imports = (
        "streamlit, pandas, numpy, scipy, statsmodels, sklearn, matplotlib, "
        "dtaidistance, arch, Ts"
    )
    isolation = (
        "import site,sys; "
        "assert site.ENABLE_USER_SITE is False; "
        "assert site.getusersitepackages() not in sys.path; "
        f"assert {str(project_root.resolve())!r} in sys.path; "
    )
    commands = [
        [
            str(runtime_python),
            "-B",
            "-c",
            f"{isolation}import {imports}; print('portable runtime imports OK')",
        ],
        [str(runtime_python), "-B", "-m", "pip", "check"],
    ]
    for command in commands:
        _run_checked(command, cwd=project_root)


def build(
    *,
    project_root: Path = PROJECT_ROOT,
    candidate_root: Path = CANDIDATE_ROOT,
    pip_wheel: Path,
) -> Path:
    """Install, verify, and manifest an already extracted candidate runtime."""

    project_root = project_root.resolve()
    expected_candidate = project_root / "build" / "runtime-candidate"
    candidate_root = assert_safe_generated_target(
        project_root,
        candidate_root,
        expected_candidate,
    )
    spec = load_portable_spec(project_root)
    pip_wheel = assert_safe_bootstrap_wheel(
        project_root,
        pip_wheel,
        pip_version=spec["pip_version"],
    )
    if sha256_file(pip_wheel) != spec["pip_wheel_sha256"]:
        raise RuntimeError("pip bootstrap wheel SHA-256 mismatch")

    lock_path = (
        project_root / "tooling" / "requirements" / "requirements-py313.lock"
    )
    runtime_python = candidate_root / "python.exe"
    if not runtime_python.is_file():
        raise RuntimeError(f"candidate Python was not found: {runtime_python}")

    write_embedded_path_file(candidate_root)
    site_packages = candidate_root / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    write_runtime_isolation(site_packages)
    write_project_root_path(site_packages, project_root)
    install_pip_bootstrap(pip_wheel, site_packages)
    install_locked_dependencies(
        runtime_python,
        lock_path,
        cwd=project_root,
    )
    remove_console_scripts(candidate_root)

    pinned = load_pinned_metadata(project_root)
    install_ts(install_root=site_packages)
    manifest = build_manifest(
        spec,
        lock_path,
        ts_commit=pinned["commit"],
    )
    (candidate_root / "runtime-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verify_runtime(runtime_python, project_root=project_root)
    return candidate_root


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=CANDIDATE_ROOT,
        help="Exact project build/runtime-candidate directory.",
    )
    parser.add_argument(
        "--pip-wheel",
        type=Path,
        required=True,
        help="Pinned pip wheel downloaded under build/portable.",
    )
    options = parser.parse_args(arguments)
    runtime_root = build(
        candidate_root=options.candidate_root,
        pip_wheel=options.pip_wheel,
    )
    print(f"Unified HTFA runtime candidate built at {runtime_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
