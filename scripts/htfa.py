"""Unified HTFA launcher, Ts runtime manager, and portable-runtime builder.

The command line has five operations:

    python scripts/htfa.py start [Streamlit arguments]
    python scripts/htfa.py setup-runtime
    python scripts/htfa.py build-runtime --candidate-root ... --pip-wheel ...
    python scripts/htfa.py install-ts [--source-root ...] [--install-root ...]
    python scripts/htfa.py stop [--port 8501]

Normal HTFA execution uses the project-local runtime.  The setup command is
stdlib-only so it can be bootstrapped by a system Python when that runtime is
missing.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import sysconfig
import tempfile
import time
import zipfile
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# These values were previously stored in ts_runtime.json and
# portable_runtime.json.  Keeping them here makes this directory self-contained.
PINNED_TS = {
    "repository": "https://github.com/BichengNiu/Ts",
    "branch": "main",
    "commit": "bec57a2610b38be3a8f78071d7e03850b53ca25e",
}
PORTABLE_RUNTIME = {
    "python_version": "3.13.4",
    "platform": "win_amd64",
    "archive_url": (
        "https://www.python.org/ftp/python/3.13.4/"
        "python-3.13.4-embed-amd64.zip"
    ),
    "archive_sha256": (
        "514ca14ec356ecb7749a7c0a1ef1eac9fd9c67d57af4812cb1f0822b0d3a85e8"
    ),
    "pip_version": "26.1.2",
    "pip_wheel_url": (
        "https://files.pythonhosted.org/packages/5d/95/6b5cb3461ea5673ba0995989746db58eb18b91b54dbf331e72f569540946/"
        "pip-26.1.2-py3-none-any.whl"
    ),
    "pip_wheel_sha256": (
        "382ff9f685ee3bc25864f820aa50505825f10f5458ffff07e30a6d96e5715cab"
    ),
}

GITHUB_REPOSITORY = "BichengNiu/Ts"
GITHUB_BRANCH = "main"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/commits/{GITHUB_BRANCH}"
GITHUB_ARCHIVE_URL = f"https://codeload.github.com/{GITHUB_REPOSITORY}/zip/{{commit}}"
RUNTIME_PACKAGES = (
    "TsMetrics",
    "TsModels",
    "TsPlots",
    "TsSims",
    "TsTests",
    "TsUtils",
)
CHECK_TIMEOUT_SECONDS = 3
DOWNLOAD_TIMEOUT_SECONDS = 30
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 50 * 1024 * 1024
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
INSTALLED_METADATA_NAME = "HTFA_RUNTIME.json"
USER_AGENT = "HTFA/1.1 Ts updater"
CANDIDATE_ROOT = PROJECT_ROOT / "build" / "runtime-candidate"


class RuntimeUpdateError(RuntimeError):
    """Raised when a Ts update or runtime installation is unsafe or fails."""


@dataclass(frozen=True)
class RuntimeSelection:
    """A Ts package root selected for the current HTFA process."""

    root: Path
    commit: str
    source: str
    detail: str


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def installed_runtime_root() -> Path:
    """Return the active interpreter's site-packages directory."""

    return Path(sysconfig.get_path("purelib")).resolve()


def load_pinned_metadata(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    """Return and validate the fixed Ts commit used for new runtimes."""

    expected = {
        "repository": f"https://github.com/{GITHUB_REPOSITORY}",
        "branch": GITHUB_BRANCH,
        "commit": PINNED_TS["commit"],
    }
    if PINNED_TS != expected or not COMMIT_PATTERN.fullmatch(expected["commit"]):
        raise RuntimeUpdateError("invalid pinned Ts metadata")
    return dict(expected)


def load_portable_spec(project_root: Path = PROJECT_ROOT) -> dict[str, str]:
    """Return and validate the fixed Python and pip bootstrap specification."""

    required = {
        "python_version",
        "platform",
        "archive_url",
        "archive_sha256",
        "pip_version",
        "pip_wheel_url",
        "pip_wheel_sha256",
    }
    if set(PORTABLE_RUNTIME) != required:
        raise ValueError("portable runtime specification fields are invalid")
    if (
        PORTABLE_RUNTIME["python_version"] != "3.13.4"
        or PORTABLE_RUNTIME["platform"] != "win_amd64"
        or PORTABLE_RUNTIME["pip_version"] != "26.1.2"
    ):
        raise ValueError("portable runtime version is invalid")
    for field in ("archive_sha256", "pip_wheel_sha256"):
        digest = PORTABLE_RUNTIME[field]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(f"portable runtime {field} is invalid")
    return dict(PORTABLE_RUNTIME)


def load_installed_metadata(root: Path | None = None) -> dict[str, str]:
    """Load the commit metadata stored inside the current Ts package."""

    package_root = (root or installed_runtime_root()).resolve() / "Ts"
    metadata_path = package_root / INSTALLED_METADATA_NAME
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeUpdateError(f"invalid installed Ts metadata: {exc}") from exc

    expected_repository = f"https://github.com/{GITHUB_REPOSITORY}"
    commit = str(metadata.get("commit", ""))
    if metadata.get("repository") != expected_repository:
        raise RuntimeUpdateError("installed Ts repository does not match the allowlist")
    if metadata.get("branch") != GITHUB_BRANCH:
        raise RuntimeUpdateError("installed Ts branch does not match the allowlist")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("installed Ts commit is not a full SHA-1")
    return {
        "repository": expected_repository,
        "branch": GITHUB_BRANCH,
        "commit": commit,
    }


def fetch_head_commit(
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: int = CHECK_TIMEOUT_SECONDS,
) -> str:
    """Return the public main HEAD through the GitHub HTTPS API."""

    request = Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeUpdateError(f"GitHub HEAD request failed: {exc}") from exc
    commit = str(payload.get("sha", "")) if isinstance(payload, dict) else ""
    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("GitHub returned an invalid commit SHA-1")
    return commit


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_archive(
    commit: str,
    archive_path: Path,
    *,
    opener: Callable[..., Any],
    timeout: int,
    max_bytes: int,
) -> None:
    request = Request(
        GITHUB_ARCHIVE_URL.format(commit=commit),
        headers={"User-Agent": USER_AGENT},
    )
    total = 0
    try:
        with opener(request, timeout=timeout) as response, archive_path.open("wb") as output:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeUpdateError("Ts archive exceeded the size limit")
                output.write(chunk)
    except RuntimeUpdateError:
        raise
    except Exception as exc:
        raise RuntimeUpdateError(f"Ts archive download failed: {exc}") from exc
    if total == 0:
        raise RuntimeUpdateError("Ts archive download was empty")


def materialize_github_runtime(
    commit: str,
    destination: Path,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    max_bytes: int = MAX_ARCHIVE_BYTES,
) -> str:
    """Download one immutable commit and extract the allowlisted Ts files."""

    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("refusing to download an invalid commit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive_path = destination.parent / f"Ts-{commit}.zip"
    try:
        _download_archive(
            commit,
            archive_path,
            opener=opener,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        archive_sha256 = sha256_file(archive_path)
        extract_runtime_archive(archive_path, destination)
        return archive_sha256
    finally:
        archive_path.unlink(missing_ok=True)


def _validate_zip_member(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename
    path = PurePosixPath(name)
    mode = info.external_attr >> 16
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or any(":" in part for part in path.parts)
        or stat.S_ISLNK(mode)
    ):
        raise RuntimeUpdateError(f"unsafe ZIP path: {name}")
    return path


def extract_runtime_archive(archive_path: Path, destination: Path) -> Path:
    """Extract only the Ts Python files needed by HTFA."""

    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeUpdateError(f"invalid Ts ZIP archive: {exc}") from exc

    with archive:
        entries = [(info, _validate_zip_member(info)) for info in archive.infolist()]
        roots = {
            path.parts[0]
            for info, path in entries
            if not info.is_dir()
            and len(path.parts) == 2
            and path.parts[1] == "__init__.py"
        }
        if len(roots) != 1:
            raise RuntimeUpdateError("Ts archive must contain one package root")
        archive_root = roots.pop()
        runtime_root = destination / "Ts"
        copied: set[PurePosixPath] = set()
        extracted_bytes = 0

        for info, path in entries:
            if info.is_dir() or path.parts[0] != archive_root:
                continue
            relative = PurePosixPath(*path.parts[1:])
            allowed = relative == PurePosixPath("__init__.py") or (
                len(relative.parts) == 2
                and relative.parts[0] in RUNTIME_PACKAGES
                and relative.suffix == ".py"
            )
            if not allowed:
                continue
            if relative in copied:
                raise RuntimeUpdateError(f"duplicate Ts runtime file: {relative}")
            extracted_bytes += info.file_size
            if extracted_bytes > MAX_EXTRACTED_BYTES:
                raise RuntimeUpdateError("extracted Ts runtime exceeded the size limit")
            target = runtime_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            copied.add(relative)

    required = {PurePosixPath("__init__.py")}
    required.update(PurePosixPath(package, "__init__.py") for package in RUNTIME_PACKAGES)
    missing = sorted(str(path) for path in required - copied)
    if missing:
        raise RuntimeUpdateError(
            "Ts archive is missing required runtime files: " + ", ".join(missing)
        )
    return destination


def _runtime_layout_is_valid(root: Path) -> bool:
    required = [root / "Ts" / "__init__.py"]
    required.extend(root / "Ts" / package / "__init__.py" for package in RUNTIME_PACKAGES)
    return all(path.is_file() for path in required)


def _clear_readonly_and_retry(function, path, error) -> None:
    if not isinstance(error, PermissionError):
        raise error
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


def _make_unique_directory(parent: Path, prefix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        candidate = parent / f"{prefix}{secrets.token_hex(4)}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeUpdateError(f"could not create a work directory in {parent}")


@contextmanager
def temporary_work_directory(parent: Path, prefix: str) -> Iterator[Path]:
    """Yield a temporary directory compatible with Windows subprocess ACLs."""

    directory = _make_unique_directory(parent, prefix)
    try:
        yield directory
    finally:
        if directory.exists():
            _remove_tree(directory)


def _make_tree_writable(path: Path) -> None:
    for entry in [path, *path.rglob("*")]:
        mode = stat.S_IRUSR | stat.S_IWUSR
        if entry.is_dir():
            mode |= stat.S_IXUSR
        os.chmod(entry, mode)


def installed_runtime_selection(root: Path | None = None) -> RuntimeSelection:
    """Return the current Ts package without importing it."""

    runtime_root = (root or installed_runtime_root()).resolve()
    if not _runtime_layout_is_valid(runtime_root):
        raise RuntimeUpdateError(
            f"Ts is not installed in the active environment: {runtime_root / 'Ts'}"
        )
    metadata = load_installed_metadata(runtime_root)
    return RuntimeSelection(
        root=runtime_root,
        commit=metadata["commit"],
        source="installed",
        detail="using the current Ts installed in this runtime",
    )


def install_ts_runtime(
    source_root: Path,
    *,
    commit: str,
    install_root: Path | None = None,
) -> RuntimeSelection:
    """Atomically replace the current Ts package without importing it."""

    source_root = source_root.resolve()
    install_root = (install_root or installed_runtime_root()).resolve()
    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("refusing to install an invalid commit")
    if not _runtime_layout_is_valid(source_root):
        raise RuntimeUpdateError(f"invalid Ts runtime layout: {source_root}")

    install_root.mkdir(parents=True, exist_ok=True)
    staging_root = _make_unique_directory(install_root, ".htfa-ts-install-")
    staged_package = staging_root / "Ts"
    target_package = install_root / "Ts"
    backup_package = staging_root / "previous-Ts"
    replaced_existing = False
    try:
        shutil.copytree(
            source_root / "Ts",
            staged_package,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        _make_tree_writable(staged_package)
        metadata = {
            "repository": f"https://github.com/{GITHUB_REPOSITORY}",
            "branch": GITHUB_BRANCH,
            "commit": commit,
            "installed_at": _timestamp(),
        }
        (staged_package / INSTALLED_METADATA_NAME).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if target_package.exists():
            os.replace(target_package, backup_package)
            replaced_existing = True
        try:
            os.replace(staged_package, target_package)
        except Exception:
            if replaced_existing and backup_package.exists():
                os.replace(backup_package, target_package)
            raise
        if backup_package.exists():
            _remove_tree(backup_package)
    finally:
        if staging_root.exists():
            _remove_tree(staging_root)

    return installed_runtime_selection(install_root)


def prepare_ts_runtime(
    *,
    project_root: Path,
    install_root: Path | None = None,
    head_fetcher: Callable[[], str] | None = None,
    candidate_materializer: Callable[[str, Path], str] | None = None,
) -> RuntimeSelection:
    """Update from public main when possible; otherwise keep the current Ts."""

    project_root.resolve()
    installed = installed_runtime_selection(install_root)
    fetch_head = head_fetcher or fetch_head_commit
    materialize = candidate_materializer or materialize_github_runtime

    try:
        head_commit = fetch_head()
    except Exception as exc:
        return replace(installed, detail=f"update check failed: {exc}")
    if head_commit == installed.commit:
        return replace(installed, detail="current Ts matches main HEAD")

    try:
        with temporary_work_directory(
            Path(tempfile.gettempdir()),
            prefix=f"htfa-ts-{head_commit[:12]}-",
        ) as temporary:
            candidate_root = temporary / "candidate"
            materialize(head_commit, candidate_root)
            updated = install_ts_runtime(
                candidate_root,
                commit=head_commit,
                install_root=install_root,
            )
        return replace(
            updated,
            source="downloaded",
            detail="updated from main HEAD",
        )
    except Exception as exc:
        return replace(installed, detail=f"update failed: {exc}")


def install(
    source_root: Path | None = None,
    install_root: Path | None = None,
) -> Path:
    """Install the pinned Ts tree into an environment."""

    metadata = load_pinned_metadata(PROJECT_ROOT)
    commit = metadata["commit"]
    if source_root is not None:
        candidate_root = source_root.resolve()
        return install_ts_runtime(
            candidate_root,
            commit=commit,
            install_root=install_root,
        ).root / "Ts"

    with temporary_work_directory(
        Path(tempfile.gettempdir()),
        prefix=f"{commit[:12]}-",
    ) as temporary:
        candidate_root = temporary / "candidate"
        materialize_github_runtime(commit, candidate_root)
        return install_ts_runtime(
            candidate_root,
            commit=commit,
            install_root=install_root,
        ).root / "Ts"


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

    lock_path = project_root / "tooling" / "requirements" / "requirements-py313.lock"
    runtime_python = candidate_root / "python.exe"
    if not runtime_python.is_file():
        raise RuntimeError(f"candidate Python was not found: {runtime_python}")

    write_embedded_path_file(candidate_root)
    site_packages = candidate_root / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    write_runtime_isolation(site_packages)
    write_project_root_path(site_packages, project_root)
    install_pip_bootstrap(pip_wheel, site_packages)
    install_locked_dependencies(runtime_python, lock_path, cwd=project_root)
    remove_console_scripts(candidate_root)

    pinned = load_pinned_metadata(project_root)
    install(install_root=site_packages)
    manifest = build_manifest(spec, lock_path, ts_commit=pinned["commit"])
    (candidate_root / "runtime-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verify_runtime(runtime_python, project_root=project_root)
    return candidate_root


def _download_verified_file(
    uri: str,
    destination: Path,
    expected_sha256: str,
) -> None:
    """Download one bootstrap artifact and remove it on any failure."""

    try:
        request = Request(uri, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response, destination.open("wb") as output:
            for chunk in iter(lambda: response.read(64 * 1024), b""):
                output.write(chunk)
        actual = sha256_file(destination)
        if actual.lower() != expected_sha256.lower():
            raise RuntimeUpdateError(f"SHA-256 mismatch for {destination}")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _extract_zip_safely(archive_path: Path, destination: Path) -> None:
    """Extract a verified ZIP without permitting path traversal."""

    destination = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        members: list[tuple[zipfile.ZipInfo, Path]] = []
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            target = destination.joinpath(*relative.parts).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise RuntimeUpdateError(
                    f"unsafe path in runtime archive: {member.filename}"
                ) from exc
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or stat.S_ISLNK(member.external_attr >> 16)
            ):
                raise RuntimeUpdateError(
                    f"unsafe path in runtime archive: {member.filename}"
                )
            members.append((member, target))
        for member, target in members:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _remove_generated_directory(path: Path) -> None:
    if path.exists():
        _remove_tree(path)


def setup_runtime(*, project_root: Path = PROJECT_ROOT) -> Path:
    """Download, build, verify, and atomically activate the portable runtime."""

    project_root = project_root.resolve()
    download_root = assert_safe_generated_target(
        project_root, project_root / "build" / "portable",
        project_root / "build" / "portable",
    )
    candidate_root = assert_safe_generated_target(
        project_root, project_root / "build" / "runtime-candidate",
        project_root / "build" / "runtime-candidate",
    )
    backup_root = assert_safe_generated_target(
        project_root, project_root / "build" / "runtime-backup",
        project_root / "build" / "runtime-backup",
    )
    runtime_root = assert_safe_generated_target(
        project_root, project_root / "runtime", project_root / "runtime",
    )

    if backup_root.exists():
        if runtime_root.exists():
            _remove_generated_directory(backup_root)
        else:
            backup_root.replace(runtime_root)
    _remove_generated_directory(download_root)
    _remove_generated_directory(candidate_root)
    download_root.mkdir(parents=True, exist_ok=True)
    candidate_root.mkdir(parents=True, exist_ok=True)

    spec = load_portable_spec(project_root)
    python_archive = download_root / "python-3.13.4-embed-amd64.zip"
    pip_wheel = download_root / f"pip-{spec['pip_version']}-py3-none-any.whl"
    print("[1/4] Downloading verified Python runtime...")
    _download_verified_file(
        spec["archive_url"], python_archive, spec["archive_sha256"]
    )
    print("[2/4] Downloading verified pip wheel...")
    _download_verified_file(
        spec["pip_wheel_url"], pip_wheel, spec["pip_wheel_sha256"]
    )
    print("[3/4] Building candidate runtime...")
    _extract_zip_safely(python_archive, candidate_root)
    candidate_python = candidate_root / "python.exe"
    if not candidate_python.is_file():
        raise RuntimeUpdateError(f"candidate Python was not extracted: {candidate_python}")
    _run_checked(
        [
            str(candidate_python),
            "-B",
            str(Path(__file__).resolve()),
            "build-runtime",
            "--candidate-root",
            str(candidate_root),
            "--pip-wheel",
            str(pip_wheel),
        ],
        cwd=project_root,
    )

    previous_runtime_moved = False
    candidate_moved = False
    try:
        if runtime_root.exists():
            runtime_root.replace(backup_root)
            previous_runtime_moved = True
        candidate_root.replace(runtime_root)
        candidate_moved = True
        print("[4/4] Running runtime smoke test...")
        _run_checked(
            [
                str(runtime_root / "python.exe"),
                "-B",
                "-c",
                "import streamlit, pandas, scipy, Ts; print('runtime smoke OK')",
            ],
            cwd=project_root,
        )
    except Exception:
        if candidate_moved and runtime_root.exists():
            _remove_generated_directory(runtime_root)
        if previous_runtime_moved and backup_root.exists():
            backup_root.replace(runtime_root)
        raise

    if backup_root.exists():
        _remove_generated_directory(backup_root)
    print(f"Unified HTFA runtime is ready at {runtime_root}")
    return runtime_root


def _listener_process_ids(port: int) -> list[int]:
    if os.name != "nt":
        return []
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
    )
    pattern = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$")
    process_ids = {
        int(match.group(1))
        for line in result.stdout.splitlines()
        if (match := pattern.match(line))
    }
    return sorted(process_ids)


def _terminate_process_tree(process_id: int) -> None:
    """Force-terminate a Windows process and every descendant process."""

    result = subprocess.run(
        ["taskkill", "/PID", str(process_id), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeUpdateError(
            f"Could not terminate process tree rooted at PID {process_id}: {detail}"
        )


def free_port(port: int = 8501, wait_seconds: int = 15) -> None:
    """Stop Windows listeners and their child processes, then verify release."""

    process_ids = _listener_process_ids(port)
    if not process_ids:
        print(f"[OK] Port {port} is available.")
        return
    for process_id in process_ids:
        print(
            f"[INFO] Stopping process tree rooted at {process_id} "
            f"on port {port}..."
        )
        try:
            _terminate_process_tree(process_id)
        except RuntimeUpdateError as exc:
            print(f"[WARN] {exc}")
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not _listener_process_ids(port):
            print(f"[OK] Port {port} released and verified.")
            return
        time.sleep(0.25)
    remaining = _listener_process_ids(port)
    raise RuntimeUpdateError(
        f"Port {port} is still in use by PID(s): {', '.join(map(str, remaining))}"
    )


def stop_backend(port: int = 8501, wait_seconds: int = 15) -> None:
    """Stop the HTFA backend process tree listening on *port*."""

    free_port(port=port, wait_seconds=wait_seconds)


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
    """Check Ts once, then start Streamlit."""

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HTFA unified launcher and runtime maintenance tool."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("start", "setup-runtime", "build-runtime", "install-ts", "stop"),
        default="start",
    )
    return parser


def cli(arguments: Sequence[str] | None = None) -> int:
    """Dispatch the compact public command line."""

    values = list(arguments if arguments is not None else sys.argv[1:])
    if values and values[0] in {"-h", "--help"}:
        _build_parser().print_help()
        print("\nUse 'start -- <Streamlit arguments>' to launch HTFA.")
        return 0
    command = values.pop(0) if values and values[0] in {
        "start", "setup-runtime", "build-runtime", "install-ts", "stop"
    } else "start"

    if command == "start":
        if values and values[0] == "--":
            values.pop(0)
        return main(values)
    if command == "setup-runtime":
        if values:
            raise SystemExit("setup-runtime does not accept arguments")
        setup_runtime()
        return 0
    if command == "install-ts":
        parser = argparse.ArgumentParser(prog="htfa.py install-ts")
        parser.add_argument("--source-root", type=Path)
        parser.add_argument("--install-root", type=Path)
        options = parser.parse_args(values)
        installed_path = install(options.source_root, options.install_root)
        print(f"Ts installed at {installed_path}")
        return 0
    if command == "stop":
        parser = argparse.ArgumentParser(prog="htfa.py stop")
        parser.add_argument("--port", type=int, default=8501)
        parser.add_argument("--wait-seconds", type=int, default=15)
        options = parser.parse_args(values)
        stop_backend(port=options.port, wait_seconds=options.wait_seconds)
        return 0
    if command == "build-runtime":
        parser = argparse.ArgumentParser(prog="htfa.py build-runtime")
        parser.add_argument("--candidate-root", type=Path, default=CANDIDATE_ROOT)
        parser.add_argument("--pip-wheel", type=Path, required=True)
        options = parser.parse_args(values)
        runtime_root = build(
            candidate_root=options.candidate_root,
            pip_wheel=options.pip_wheel,
        )
        print(f"Unified HTFA runtime candidate built at {runtime_root}")
        return 0
    raise AssertionError(f"unknown command: {command}")


__all__ = [
    "RuntimeSelection",
    "RuntimeUpdateError",
    "activate_ts_runtime",
    "assert_safe_bootstrap_wheel",
    "assert_safe_generated_target",
    "build",
    "build_manifest",
    "build_streamlit_argv",
    "cli",
    "extract_runtime_archive",
    "fetch_head_commit",
    "format_selection_message",
    "free_port",
    "stop_backend",
    "install",
    "install_locked_dependencies",
    "install_pip_bootstrap",
    "install_ts_runtime",
    "installed_runtime_root",
    "installed_runtime_selection",
    "load_installed_metadata",
    "load_pinned_metadata",
    "load_portable_spec",
    "main",
    "materialize_github_runtime",
    "prepare_ts_runtime",
    "setup_runtime",
    "sha256_file",
    "temporary_work_directory",
    "verify_runtime",
]


if __name__ == "__main__":
    raise SystemExit(cli())
