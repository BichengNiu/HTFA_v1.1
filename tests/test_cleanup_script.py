"""Workspace cleanup removes generated files without crossing data boundaries."""

from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows cleanup script")
SCRIPT = Path(__file__).parents[1] / "tooling/scripts/clean_temps.ps1"


def _project(tmp_path):
    root = tmp_path / "workspace"
    script = root / "tooling/scripts/clean_temps.ps1"
    script.parent.mkdir(parents=True)
    shutil.copy2(SCRIPT, script)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    return root, script


def _put(root, name, payload=b"keep"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _run(script, *options):
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *options],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        timeout=60,
    )


def test_cleanup_removes_temporary_files_but_preserves_data_and_tracked_sources(tmp_path):
    root, script = _project(tmp_path)
    protected = [
        "data/UAE/uae.duckdb", "data/UAE/阿联酋.xlsx", "data/UAE/.env",
        "data/UAE/raw/__pycache__/keep.pyc", "data/UAE/raw/keep.tmp",
        "data/工业/keep.log", "data/暂存/keep.tmp", "users.db",
        "references-local/keep.tmp", ".git/keep.tmp", "_tracked.py",
    ]
    for name in protected:
        _put(root, name)
    subprocess.run(["git", "-C", str(root), "add", "--", "_tracked.py"], check=True)
    temporary = ["_probe.py", "scratch/__pycache__/remove.pyc", "scratch/output.log",
                 "data/UAE/processed/test.csv", ".cache/probe.py", ".cache/before/uae.duckdb"]
    for name in temporary:
        _put(root, name, b"temporary")
    _run(script, "-IncludeAgentCache")
    assert all((root / name).read_bytes() == b"keep" for name in protected)
    assert all(not (root / name).exists() for name in temporary)
    assert not (root / ".cache").exists()
    assert script.read_bytes().startswith(b"\xef\xbb\xbf")


def test_agent_cache_purge_requires_explicit_option(tmp_path):
    root, script = _project(tmp_path)
    evidence = _put(root, ".cache/inspection.py")
    _run(script)
    assert evidence.read_bytes() == b"keep"
    _run(script, "-IncludeAgentCache")
    assert not evidence.exists()


def test_cleanup_does_not_follow_directory_junctions(tmp_path):
    root, script = _project(tmp_path)
    outside = tmp_path / "outside"
    sentinel = _put(outside, "__pycache__/keep.pyc")
    _put(outside, "keep.log")
    cache = root / ".cache"
    cache.mkdir()
    junction = cache / "linked"
    # Both paths are fixture-owned; only the junction itself is removed below.
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "New-Item -ItemType Junction -Path $env:HTFA_TEST_LINK "
         "-Target $env:HTFA_TEST_TARGET | Out-Null"],
        env={**os.environ, "HTFA_TEST_LINK": str(junction), "HTFA_TEST_TARGET": str(outside)},
        check=True, capture_output=True, timeout=30,
    )
    try:
        result = _run(script, "-IncludeAgentCache")
        assert "skipped" in result.stdout
        assert sentinel.read_bytes() == b"keep"
        assert (outside / "keep.log").read_bytes() == b"keep"
    finally:
        if junction.exists():
            junction.rmdir()
