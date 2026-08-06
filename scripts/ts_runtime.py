"""Prepare and activate a validated Ts runtime for local HTFA startup."""

from __future__ import annotations

import hashlib
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
import zipfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

GITHUB_REPOSITORY = "BichengNiu/Ts"
GITHUB_BRANCH = "main"
GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_REPOSITORY}.git"
RUNTIME_PACKAGES = (
    "TsMetrics",
    "TsModels",
    "TsPlots",
    "TsSims",
    "TsTests",
    "TsUtils",
)
REQUIRED_INTERFACES = (
    "TimeSeriesSummary",
    "difference",
    "plot_acf",
    "plot_pacf",
    "plot_series",
    "ADFTest",
    "KPSSTest",
    "PhillipsPerronTest",
    "ZivotAndrewsTest",
)
CHECK_TIMEOUT_SECONDS = 3
DOWNLOAD_TIMEOUT_SECONDS = 30
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_BYTES = 50 * 1024 * 1024
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
INSTALLED_METADATA_NAME = "HTFA_RUNTIME.json"


class RuntimeUpdateError(RuntimeError):
    """Raised when a candidate Ts runtime cannot be trusted or activated."""


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
    """Return the environment package root containing the installed Ts package."""

    return Path(sysconfig.get_path("purelib")).resolve()


def default_cache_root() -> Path:
    """Return the Ts update cache inside the active Python environment."""

    return installed_runtime_root() / ".htfa-ts-runtime"


def load_pinned_metadata(project_root: Path) -> dict[str, str]:
    """Load and validate the pinned bootstrap version metadata."""

    metadata_path = project_root / "scripts" / "ts_runtime.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeUpdateError(f"invalid pinned Ts metadata: {exc}") from exc

    expected_repository = f"https://github.com/{GITHUB_REPOSITORY}"
    if metadata.get("repository") != expected_repository:
        raise RuntimeUpdateError("pinned Ts repository does not match the allowlist")
    if metadata.get("branch") != GITHUB_BRANCH:
        raise RuntimeUpdateError("pinned Ts branch does not match the allowlist")
    commit = str(metadata.get("commit", ""))
    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("pinned Ts commit is not a full SHA-1")
    return {
        "repository": expected_repository,
        "branch": GITHUB_BRANCH,
        "commit": commit,
    }


def load_installed_metadata(root: Path | None = None) -> dict[str, str]:
    """Load validated metadata from the Ts package installed in the environment."""

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


def read_state(state_path: Path) -> dict[str, Any]:
    """Read updater state; corrupt or absent state is treated as empty."""

    try:
        value = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(state_path: Path, state: dict[str, Any]) -> None:
    """Atomically write updater state in the cache filesystem."""

    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(state, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, state_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


class UpdateLock(AbstractContextManager[bool]):
    """A non-blocking cross-platform file lock for cache writers."""

    def __init__(self, path: Path):
        self.path = path
        self._handle: BinaryIO | None = None
        self._acquired = False

    def __enter__(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a+b")
            self._handle.seek(0, os.SEEK_END)
            if self._handle.tell() == 0:
                self._handle.write(b"0")
                self._handle.flush()
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._acquired = True
        except (OSError, BlockingIOError):
            if self._handle is not None:
                self._handle.close()
                self._handle = None
        return self._acquired

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            if self._acquired and os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif self._acquired:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
            self._acquired = False


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    return environment


def _run_git(
    arguments: list[str],
    *,
    timeout: int,
    runner: Callable[..., Any] = subprocess.run,
) -> Any:
    try:
        completed = runner(
            ["git", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeUpdateError(f"Git is unavailable or timed out: {exc}") from exc
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "unknown Git error").strip()
        raise RuntimeUpdateError(f"Git command failed: {error}")
    return completed


def fetch_head_commit(
    *,
    runner: Callable[..., Any] = subprocess.run,
    timeout: int = CHECK_TIMEOUT_SECONDS,
) -> str:
    """Resolve private or public main HEAD through the user's Git credentials."""

    completed = _run_git(
        ["ls-remote", GITHUB_REPOSITORY_URL, f"refs/heads/{GITHUB_BRANCH}"],
        timeout=timeout,
        runner=runner,
    )
    fields = completed.stdout.strip().split()
    commit = fields[0] if fields else ""
    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("Git returned an invalid commit SHA-1")
    return commit


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_git_runtime(
    commit: str,
    destination: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    max_bytes: int = MAX_ARCHIVE_BYTES,
) -> str:
    """Fetch one private-repository commit and materialize allowlisted runtime files."""

    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("refusing to fetch an invalid commit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    repository = destination.parent / "source.git"
    archive_path = destination.parent / "Ts.git.zip"
    _run_git(["init", "--quiet", str(repository)], timeout=timeout, runner=runner)
    _run_git(
        ["-C", str(repository), "remote", "add", "origin", GITHUB_REPOSITORY_URL],
        timeout=timeout,
        runner=runner,
    )
    _run_git(
        [
            "-C",
            str(repository),
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "origin",
            commit,
        ],
        timeout=timeout,
        runner=runner,
    )
    resolved = _run_git(
        ["-C", str(repository), "rev-parse", "FETCH_HEAD"],
        timeout=timeout,
        runner=runner,
    ).stdout.strip()
    if resolved != commit:
        raise RuntimeUpdateError(
            f"fetched commit mismatch: expected {commit}, got {resolved}"
        )
    _run_git(
        [
            "-C",
            str(repository),
            "archive",
            "--format=zip",
            f"--prefix=Ts-{commit}/",
            f"--output={archive_path}",
            "FETCH_HEAD",
        ],
        timeout=timeout,
        runner=runner,
    )
    try:
        archive_size = archive_path.stat().st_size
    except OSError as exc:
        raise RuntimeUpdateError(f"Git did not create the Ts archive: {exc}") from exc
    if archive_size == 0 or archive_size > max_bytes:
        raise RuntimeUpdateError("Ts archive exceeded the size limit")
    archive_sha256 = _sha256_file(archive_path)
    extract_runtime_archive(archive_path, destination)
    return archive_sha256


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
    """Extract only the allowlisted Python runtime files from a Ts archive."""

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
    """Create a private work directory without restrictive cloud-drive ACLs."""

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
    """Remove copied read-only attributes without changing file contents."""

    for entry in [path, *path.rglob("*")]:
        mode = stat.S_IRUSR | stat.S_IWUSR
        if entry.is_dir():
            mode |= stat.S_IXUSR
        os.chmod(entry, mode)


def installed_runtime_selection(root: Path | None = None) -> RuntimeSelection:
    """Return the Ts runtime installed alongside the environment dependencies."""

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
        detail="using Ts installed in the active Python environment",
    )


def install_ts_runtime(
    source_root: Path,
    *,
    commit: str,
    install_root: Path | None = None,
) -> RuntimeSelection:
    """Atomically install a validated Ts source tree into site-packages."""

    source_root = source_root.resolve()
    install_root = (install_root or installed_runtime_root()).resolve()
    if not COMMIT_PATTERN.fullmatch(commit):
        raise RuntimeUpdateError("refusing to install an invalid Ts commit")
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
        write_state(
            staged_package / INSTALLED_METADATA_NAME,
            {
                "repository": f"https://github.com/{GITHUB_REPOSITORY}",
                "branch": GITHUB_BRANCH,
                "commit": commit,
                "installed_at": _timestamp(),
            },
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


def smoke_test_runtime(
    root: Path,
    *,
    python_executable: str = sys.executable,
    timeout: int = 20,
) -> None:
    """Import the candidate in an isolated child process using the current Python."""

    expected = (root / "Ts").resolve()
    code = """
from pathlib import Path
import Ts
from Ts import TimeSeriesSummary, difference
from Ts.TsPlots import plot_acf, plot_pacf, plot_series
from Ts.TsTests import ADFTest, KPSSTest, PhillipsPerronTest, ZivotAndrewsTest
expected = Path.cwd().joinpath('Ts').resolve()
actual = Path(Ts.__file__).resolve().parent
assert actual == expected, f'wrong Ts import: {actual}'
assert all(callable(item) for item in (
    TimeSeriesSummary, difference, plot_acf, plot_pacf, plot_series,
    ADFTest, KPSSTest, PhillipsPerronTest, ZivotAndrewsTest,
))
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    try:
        completed = subprocess.run(
            [python_executable, "-c", code],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeUpdateError(f"Ts candidate smoke test failed: {exc}") from exc
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout).strip()
        raise RuntimeUpdateError(f"Ts candidate smoke test failed: {output}")
    if not expected.is_dir():
        raise RuntimeUpdateError("Ts candidate disappeared after its smoke test")


def _read_version_metadata(version_root: Path) -> dict[str, Any] | None:
    metadata = read_state(version_root / "metadata.json")
    commit = str(metadata.get("commit", ""))
    if (
        version_root.name != commit
        or not COMMIT_PATTERN.fullmatch(commit)
        or not _runtime_layout_is_valid(version_root)
    ):
        return None
    return metadata


def _cached_selections(cache_root: Path) -> list[RuntimeSelection]:
    versions_root = cache_root / "versions"
    if not versions_root.is_dir():
        return []
    candidates: list[tuple[str, RuntimeSelection]] = []
    for version_root in versions_root.iterdir():
        if not version_root.is_dir():
            continue
        metadata = _read_version_metadata(version_root)
        if metadata is None:
            continue
        verified_at = str(metadata.get("verified_at", ""))
        selection = RuntimeSelection(
            root=version_root,
            commit=str(metadata["commit"]),
            source="cached",
            detail="using a previously verified Ts runtime",
        )
        candidates.append((verified_at, selection))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [selection for _, selection in candidates]


def _fallback_selection(
    cache_root: Path,
    state: dict[str, Any],
    install_root: Path | None = None,
) -> RuntimeSelection:
    cached = _cached_selections(cache_root)
    active_commit = state.get("active_commit")
    for selection in cached:
        if selection.commit == active_commit:
            return selection
    if cached:
        return cached[0]
    return installed_runtime_selection(install_root)


def _safe_write_state(state_path: Path, state: dict[str, Any]) -> None:
    try:
        write_state(state_path, state)
    except OSError:
        pass


def _failure_state(
    state: dict[str, Any],
    fallback: RuntimeSelection,
    error: Exception | str,
) -> dict[str, Any]:
    updated = dict(state)
    updated.update(
        {
            "active_commit": fallback.commit,
            "last_check_at": _timestamp(),
            "last_error": str(error),
        }
    )
    return updated


def _prune_versions(cache_root: Path, active_commit: str, keep: int = 2) -> None:
    candidates = _cached_selections(cache_root)
    keep_commits = {active_commit}
    for selection in candidates:
        if len(keep_commits) >= keep:
            break
        keep_commits.add(selection.commit)
    for selection in candidates:
        if selection.commit not in keep_commits:
            _remove_tree(selection.root)


def prepare_ts_runtime(
    *,
    project_root: Path,
    cache_root: Path | None = None,
    head_fetcher: Callable[[], str] | None = None,
    candidate_materializer: Callable[[str, Path], str] | None = None,
    python_executable: str = sys.executable,
) -> RuntimeSelection:
    """Select the latest validated runtime without risking HTFA availability."""

    project_root = project_root.resolve()
    installed = installed_runtime_selection()
    cache_root = (cache_root or default_cache_root()).resolve()
    state_path = cache_root / "state.json"
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return replace(installed, detail=f"Ts cache is unavailable: {exc}")

    state = read_state(state_path)
    fallback = _fallback_selection(cache_root, state)

    with UpdateLock(cache_root / "update.lock") as acquired:
        if not acquired:
            return replace(fallback, detail="another HTFA process is checking Ts")

        try:
            head_commit = (head_fetcher or fetch_head_commit)()
        except Exception as exc:  # noqa: BLE001 - network failures must fall back
            _safe_write_state(state_path, _failure_state(state, fallback, exc))
            return replace(fallback, detail=str(exc))

        cached_by_commit = {
            selection.commit: selection for selection in _cached_selections(cache_root)
        }
        if head_commit in cached_by_commit:
            selected = cached_by_commit[head_commit]
            _safe_write_state(
                state_path,
                {
                    **state,
                    "active_commit": selected.commit,
                    "last_check_at": _timestamp(),
                    "last_error": None,
                },
            )
            return replace(selected, detail="the cached Ts runtime matches main HEAD")

        if head_commit == installed.commit:
            _safe_write_state(
                state_path,
                {
                    **state,
                    "active_commit": installed.commit,
                    "last_check_at": _timestamp(),
                    "last_error": None,
                },
            )
            return replace(installed, detail="the installed Ts runtime matches main HEAD")

        staging_parent = cache_root / "staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging_root = _make_unique_directory(
            staging_parent,
            f"{head_commit[:12]}-",
        )
        try:
            candidate_root = staging_root / "candidate"
            materialize = candidate_materializer or materialize_git_runtime
            archive_sha256 = materialize(head_commit, candidate_root)
            smoke_test_runtime(
                candidate_root,
                python_executable=python_executable,
            )
            verified_at = _timestamp()
            write_state(
                candidate_root / "metadata.json",
                {
                    "archive_sha256": archive_sha256,
                    "commit": head_commit,
                    "verified_at": verified_at,
                },
            )
            versions_root = cache_root / "versions"
            versions_root.mkdir(parents=True, exist_ok=True)
            final_root = versions_root / head_commit
            if final_root.exists():
                shutil.rmtree(final_root)
            os.replace(candidate_root, final_root)
            selected = RuntimeSelection(
                root=final_root,
                commit=head_commit,
                source="downloaded",
                detail="downloaded and verified main HEAD",
            )
            write_state(
                state_path,
                {
                    **state,
                    "active_commit": head_commit,
                    "archive_sha256": archive_sha256,
                    "last_check_at": verified_at,
                    "last_error": None,
                },
            )
            _prune_versions(cache_root, head_commit)
            return selected
        except Exception as exc:  # noqa: BLE001 - candidate failures must fall back
            _safe_write_state(state_path, _failure_state(state, fallback, exc))
            return replace(fallback, detail=str(exc))
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)


__all__ = [
    "RuntimeSelection",
    "RuntimeUpdateError",
    "UpdateLock",
    "default_cache_root",
    "extract_runtime_archive",
    "fetch_head_commit",
    "install_ts_runtime",
    "installed_runtime_root",
    "installed_runtime_selection",
    "load_installed_metadata",
    "load_pinned_metadata",
    "materialize_git_runtime",
    "prepare_ts_runtime",
    "read_state",
    "smoke_test_runtime",
    "temporary_work_directory",
    "write_state",
]
