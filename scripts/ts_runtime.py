"""Install the newest Ts main commit before launching HTFA."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sysconfig
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.request import Request, urlopen

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


class RuntimeUpdateError(RuntimeError):
    """Raised when a Ts update cannot be downloaded or installed safely."""


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


def load_pinned_metadata(project_root: Path) -> dict[str, str]:
    """Load the fixed Ts commit bundled into a new runtime."""

    metadata_path = project_root / "scripts" / "ts_runtime.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeUpdateError(f"invalid pinned Ts metadata: {exc}") from exc

    expected_repository = f"https://github.com/{GITHUB_REPOSITORY}"
    commit = str(metadata.get("commit", ""))
    if metadata.get("repository") != expected_repository:
        raise RuntimeUpdateError("pinned Ts repository does not match the allowlist")
    if metadata.get("branch") != GITHUB_BRANCH:
        raise RuntimeUpdateError("pinned Ts branch does not match the allowlist")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("pinned Ts commit is not a full SHA-1")
    return {
        "repository": expected_repository,
        "branch": GITHUB_BRANCH,
        "commit": commit,
    }


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


def _sha256_file(path: Path) -> str:
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
        archive_sha256 = _sha256_file(archive_path)
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


__all__ = [
    "RuntimeSelection",
    "RuntimeUpdateError",
    "extract_runtime_archive",
    "fetch_head_commit",
    "install_ts_runtime",
    "installed_runtime_root",
    "installed_runtime_selection",
    "load_installed_metadata",
    "load_pinned_metadata",
    "materialize_github_runtime",
    "prepare_ts_runtime",
    "temporary_work_directory",
]
