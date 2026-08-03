import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from scripts.ts_runtime import (
    RuntimeUpdateError,
    UpdateLock,
    extract_runtime_archive,
    fetch_head_commit,
    prepare_ts_runtime,
    read_state,
    write_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDORED_COMMIT = "bec57a2610b38be3a8f78071d7e03850b53ca25e"
REMOTE_COMMIT = "1" * 40


def _runtime_zip(commit: str) -> bytes:
    output = io.BytesIO()
    prefix = f"Ts-{commit}"
    with zipfile.ZipFile(output, "w") as archive:
        for source in (PROJECT_ROOT / "Ts").rglob("*.py"):
            relative = source.relative_to(PROJECT_ROOT / "Ts")
            archive.writestr(
                f"{prefix}/{relative.as_posix()}",
                source.read_bytes(),
            )
    return output.getvalue()


def _head_fetcher(commit: str):
    def fetch() -> str:
        return commit

    return fetch


def _offline_head_fetcher() -> str:
    raise OSError("offline")


def _candidate_materializer(*, broken_init: bool = False):
    def materialize(commit: str, destination: Path) -> str:
        shutil.copytree(
            PROJECT_ROOT / "Ts",
            destination / "Ts",
            ignore=shutil.ignore_patterns("__pycache__", "VENDORED.*"),
        )
        if broken_init:
            (destination / "Ts" / "__init__.py").write_text(
                "raise ImportError('candidate dependency missing')\n",
                encoding="utf-8",
            )
        return commit * 2

    return materialize


def _seed_cached_version(cache_root: Path, commit: str, verified_at: str) -> None:
    version_root = cache_root / "versions" / commit
    shutil.copytree(
        PROJECT_ROOT / "Ts",
        version_root / "Ts",
        ignore=shutil.ignore_patterns("__pycache__", "VENDORED.*"),
    )
    write_state(
        version_root / "metadata.json",
        {
            "archive_sha256": commit,
            "commit": commit,
            "verified_at": verified_at,
        },
    )


def test_state_round_trip_is_json(tmp_path):
    state_path = tmp_path / "state.json"
    expected = {
        "active_commit": REMOTE_COMMIT,
        "last_check_at": "2026-08-03T00:00:00+00:00",
        "last_error": None,
    }

    write_state(state_path, expected)

    assert read_state(state_path) == expected
    assert json.loads(state_path.read_text(encoding="utf-8")) == expected


def test_offline_without_cache_uses_vendored_version(tmp_path):
    selection = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        cache_root=tmp_path,
        head_fetcher=_offline_head_fetcher,
    )

    assert selection.commit == VENDORED_COMMIT
    assert selection.root == PROJECT_ROOT
    assert selection.source == "vendored"
    assert "offline" in selection.detail


def test_corrupt_state_does_not_break_offline_fallback(tmp_path):
    (tmp_path / "state.json").write_text("{broken", encoding="utf-8")

    selection = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        cache_root=tmp_path,
        head_fetcher=_offline_head_fetcher,
    )

    assert selection.commit == VENDORED_COMMIT
    assert selection.source == "vendored"


def test_valid_remote_version_is_downloaded_verified_and_reused(tmp_path):
    first = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        cache_root=tmp_path,
        head_fetcher=_head_fetcher(REMOTE_COMMIT),
        candidate_materializer=_candidate_materializer(),
    )

    assert first.commit == REMOTE_COMMIT
    assert first.source == "downloaded"
    assert first.root == tmp_path / "versions" / REMOTE_COMMIT
    assert (first.root / "Ts" / "TsTests" / "__init__.py").exists()

    second = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        cache_root=tmp_path,
        head_fetcher=_head_fetcher(REMOTE_COMMIT),
        candidate_materializer=lambda *_: pytest.fail("downloaded twice"),
    )

    assert second.commit == REMOTE_COMMIT
    assert second.source == "cached"


def test_invalid_remote_version_keeps_last_good_version(tmp_path):
    good = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        cache_root=tmp_path,
        head_fetcher=_head_fetcher(REMOTE_COMMIT),
        candidate_materializer=_candidate_materializer(),
    )
    broken_commit = "2" * 40

    fallback = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        cache_root=tmp_path,
        head_fetcher=_head_fetcher(broken_commit),
        candidate_materializer=_candidate_materializer(broken_init=True),
    )

    assert fallback.commit == good.commit
    assert fallback.source == "cached"
    assert "candidate dependency missing" in fallback.detail
    assert read_state(tmp_path / "state.json")["active_commit"] == good.commit


def test_extract_rejects_zip_path_traversal(tmp_path):
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Ts-bad/__init__.py", b"")
        archive.writestr("Ts-bad/../outside.py", b"bad")

    with pytest.raises(RuntimeUpdateError, match="unsafe ZIP path"):
        extract_runtime_archive(archive_path, tmp_path / "candidate")


def test_extract_accepts_git_generated_runtime_archive(tmp_path):
    archive_path = tmp_path / "runtime.zip"
    archive_path.write_bytes(_runtime_zip(REMOTE_COMMIT))

    root = extract_runtime_archive(archive_path, tmp_path / "candidate")

    assert (root / "Ts" / "TsUtils" / "__init__.py").exists()


def test_git_head_parser_requires_a_full_commit():
    class Completed:
        returncode = 0
        stdout = "short\trefs/heads/main\n"
        stderr = ""

    with pytest.raises(RuntimeUpdateError, match="invalid commit"):
        fetch_head_commit(runner=lambda *args, **kwargs: Completed())


def test_busy_update_lock_skips_network_and_uses_fallback(tmp_path):
    head_calls = []

    def fetch_head():
        head_calls.append(True)
        return REMOTE_COMMIT

    with UpdateLock(tmp_path / "update.lock") as acquired:
        assert acquired
        selection = prepare_ts_runtime(
            project_root=PROJECT_ROOT,
            cache_root=tmp_path,
            head_fetcher=fetch_head,
        )

    assert selection.source == "vendored"
    assert "another HTFA process" in selection.detail
    assert head_calls == []


def test_successful_update_retains_only_two_verified_online_versions(tmp_path):
    oldest = "3" * 40
    previous = "4" * 40
    newest = "5" * 40
    _seed_cached_version(tmp_path, oldest, "2026-08-01T00:00:00+00:00")
    _seed_cached_version(tmp_path, previous, "2026-08-02T00:00:00+00:00")
    write_state(tmp_path / "state.json", {"active_commit": previous})

    selected = prepare_ts_runtime(
        project_root=PROJECT_ROOT,
        cache_root=tmp_path,
        head_fetcher=_head_fetcher(newest),
        candidate_materializer=_candidate_materializer(),
    )

    remaining = {
        path.name
        for path in (tmp_path / "versions").iterdir()
        if path.is_dir()
    }
    assert selected.commit == newest
    assert remaining == {previous, newest}
