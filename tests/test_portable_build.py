import hashlib
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import build_portable

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_builder_runs_as_a_script():
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_portable.py"), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_portable_spec_pins_python_3134_and_official_sha256():
    spec = build_portable.load_portable_spec(PROJECT_ROOT)

    assert spec == {
        "python_version": "3.13.4",
        "platform": "win_amd64",
        "archive_url": (
            "https://www.python.org/ftp/python/3.13.4/"
            "python-3.13.4-embed-amd64.zip"
        ),
        "archive_sha256": (
            "514ca14ec356ecb7749a7c0a1ef1eac9"
            "fd9c67d57af4812cb1f0822b0d3a85e8"
        ),
    }


def test_builder_targets_project_root_runtime():
    assert build_portable.RUNTIME_ROOT == PROJECT_ROOT / "runtime"


def test_portable_lock_contains_only_exact_pins():
    lock_path = PROJECT_ROOT / "requirements-win-py313.lock"
    requirements = [
        line.strip()
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert requirements
    assert all(line.count("==") == 1 for line in requirements)
    assert all(";" not in line and " @ " not in line for line in requirements)
    assert len(requirements) == len({line.casefold() for line in requirements})


def test_dependency_install_disables_bytecode_compilation(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        build_portable,
        "_run_checked",
        lambda arguments, *, cwd: calls.append((arguments, cwd)),
    )

    build_portable.install_locked_dependencies(
        tmp_path / "builder.exe",
        tmp_path / "runtime.exe",
        tmp_path / "requirements.lock",
        cwd=tmp_path,
    )

    assert len(calls) == 1
    assert "--no-compile" in calls[0][0]


def test_runtime_verification_disables_bytecode_writes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        build_portable,
        "_run_checked",
        lambda arguments, *, cwd: calls.append((arguments, cwd)),
    )

    build_portable.verify_runtime(tmp_path / "runtime.exe", project_root=tmp_path)

    assert len(calls) == 1
    assert calls[0][0][1] == "-B"


def test_builder_refuses_cleanup_outside_approved_runtime(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime_root = project_root / "runtime"

    with pytest.raises(ValueError, match="unsafe generated target"):
        build_portable.assert_safe_generated_target(
            project_root,
            tmp_path / "outside",
            runtime_root,
        )

    assert build_portable.assert_safe_generated_target(
        project_root,
        runtime_root,
        runtime_root,
    ) == runtime_root.resolve()


def test_builder_resets_readonly_generated_directory(tmp_path):
    project_root = tmp_path / "project"
    target = project_root / "build" / "portable"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old\n", encoding="utf-8")
    target.chmod(stat.S_IREAD)

    result = build_portable._reset_generated_directory(
        project_root, target, target
    )

    assert result == target.resolve()
    assert list(result.iterdir()) == []


def test_builder_removes_generated_console_scripts(tmp_path):
    runtime_root = tmp_path / "runtime"
    scripts_root = runtime_root / "Scripts"
    scripts_root.mkdir(parents=True)
    (scripts_root / "tool.exe").write_bytes(b"launcher")

    build_portable.remove_console_scripts(runtime_root)

    assert not scripts_root.exists()


def test_builder_writes_embedded_python_path_file(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()

    path_file = build_portable.write_embedded_path_file(runtime_root)

    assert path_file.name == "python313._pth"
    assert path_file.read_text(encoding="utf-8").splitlines() == [
        "python313.zip",
        ".",
        "Lib",
        "Lib/site-packages",
        "import site",
    ]



def test_builder_manifest_records_python_dependencies_and_ts(tmp_path):
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("demo==1.0\n", encoding="utf-8")
    spec = {
        "python_version": "3.13.4",
        "platform": "win_amd64",
        "archive_sha256": "a" * 64,
    }

    manifest = build_portable.build_manifest(
        spec,
        lock_path,
        ts_commit="b" * 40,
        built_at="2026-08-11T00:00:00+00:00",
    )

    assert manifest["python"] == spec
    assert manifest["dependency_lock"]["sha256"] == hashlib.sha256(lock_path.read_bytes()).hexdigest()
    assert manifest["ts_commit"] == "b" * 40
    assert manifest["built_at"] == "2026-08-11T00:00:00+00:00"
