import hashlib
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts import build_portable

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_setup_batch_uses_only_powershell_bootstrap():
    batch = (
        PROJECT_ROOT / "scripts" / "windows" / "setup_runtime.bat"
    ).read_text(encoding="utf-8")
    lower = batch.lower()

    assert "powershell -noprofile" in lower
    assert "scripts\\bootstrap_runtime.ps1" in lower
    assert ".venv" not in lower
    assert "pip" not in lower
    assert not any(
        line.lstrip().startswith(("py ", "python "))
        for line in lower.splitlines()
    )


def test_bootstrap_script_validates_candidate_before_safe_swap():
    script = (PROJECT_ROOT / "scripts" / "bootstrap_runtime.ps1").read_text(
        encoding="utf-8"
    )

    required_fragments = (
        "build\\portable",
        "build\\runtime-candidate",
        "build\\runtime-backup",
        "runtime",
        "Get-FileHash",
        "archive_sha256",
        "pip_wheel_sha256",
        "scripts\\build_portable.py",
        '"-m", "pytest", "-q"',
        '"-c", "tooling\\pytest.ini"',
        '"-m", "compileall"',
        "Move-Item -LiteralPath",
        "Restore-RuntimeBackup",
    )
    assert all(fragment in script for fragment in required_fragments)

    build_position = script.index("scripts\\build_portable.py")
    pytest_position = script.index('"-m", "pytest", "-q"')
    swap_position = script.index(
        "Move-Item -LiteralPath $runtimeRootPath -Destination $backupRootPath"
    )
    assert build_position < pytest_position < swap_position


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
        "pip_version": "26.1.2",
        "pip_wheel_url": (
            "https://files.pythonhosted.org/packages/5d/95/"
            "6b5cb3461ea5673ba0995989746db58eb18b91b54dbf331e72f569540946/"
            "pip-26.1.2-py3-none-any.whl"
        ),
        "pip_wheel_sha256": (
            "382ff9f685ee3bc25864f820aa5050582"
            "5f10f5458ffff07e30a6d96e5715cab"
        ),
    }


def test_builder_targets_candidate_not_active_runtime():
    assert (
        build_portable.CANDIDATE_ROOT
        == PROJECT_ROOT / "build" / "runtime-candidate"
    )


def test_portable_lock_contains_only_exact_pins():
    lock_path = (
        PROJECT_ROOT / "tooling" / "requirements" / "requirements-py313.lock"
    )
    requirements = [
        line.strip()
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert requirements
    assert all(line.count("==") == 1 for line in requirements)
    assert all(";" not in line and " @ " not in line for line in requirements)
    assert len(requirements) == len({line.casefold() for line in requirements})
    assert "pip==26.1.2" in requirements
    assert "pytest==9.0.2" in requirements
    assert "iniconfig==2.3.0" in requirements
    assert "pluggy==1.6.0" in requirements
    assert "pygments==2.20.0" in requirements


def test_pip_bootstrap_extracts_the_pinned_wheel(tmp_path):
    wheel = tmp_path / "pip.whl"
    site_packages = tmp_path / "site-packages"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("pip/__init__.py", "__version__ = '26.1.2'\n")
        archive.writestr(
            "pip-26.1.2.dist-info/METADATA",
            "Name: pip\nVersion: 26.1.2\n",
        )

    build_portable.install_pip_bootstrap(wheel, site_packages)

    assert (site_packages / "pip" / "__init__.py").is_file()
    assert (site_packages / "pip-26.1.2.dist-info" / "METADATA").is_file()


def test_pip_bootstrap_rejects_path_traversal(tmp_path):
    wheel = tmp_path / "pip.whl"
    site_packages = tmp_path / "site-packages"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("../escaped.py", "raise SystemExit\n")

    with pytest.raises(ValueError, match="unsafe path in pip wheel"):
        build_portable.install_pip_bootstrap(wheel, site_packages)

    assert not (tmp_path / "escaped.py").exists()


def test_locked_dependencies_use_candidate_python_module_pip(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        build_portable,
        "_run_checked",
        lambda arguments, *, cwd: calls.append((arguments, cwd)),
    )

    build_portable.install_locked_dependencies(
        tmp_path / "python.exe",
        tmp_path / "requirements.lock",
        cwd=tmp_path,
    )

    assert len(calls) == 1
    arguments = calls[0][0]
    assert arguments[:5] == [
        str(tmp_path / "python.exe"),
        "-I",
        "-B",
        "-m",
        "pip",
    ]
    assert "--no-compile" in arguments


def test_runtime_verification_checks_pip_pytest_and_imports(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        build_portable,
        "_run_checked",
        lambda arguments, *, cwd: calls.append((arguments, cwd)),
    )

    build_portable.verify_runtime(tmp_path / "runtime.exe", project_root=tmp_path)

    assert len(calls) == 3
    joined = [" ".join(arguments) for arguments, _ in calls]
    assert all(arguments[1] == "-B" for arguments, _ in calls)
    assert any("-m pip check" in call for call in joined)
    assert any("-m pytest --version" in call for call in joined)
    assert any("portable runtime imports OK" in call for call in joined)


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


def test_builder_writes_user_site_isolation(tmp_path):
    site_packages = tmp_path / "Lib" / "site-packages"

    sitecustomize = build_portable.write_runtime_isolation(site_packages)

    content = sitecustomize.read_text(encoding="utf-8")
    assert sitecustomize == site_packages / "sitecustomize.py"
    assert "site.getusersitepackages()" in content
    assert "site.ENABLE_USER_SITE = False" in content
    assert "sys.path[:]" in content


def test_builder_writes_project_root_path(tmp_path):
    project_root = tmp_path / "project"
    site_packages = tmp_path / "runtime" / "Lib" / "site-packages"
    project_root.mkdir()

    path_file = build_portable.write_project_root_path(
        site_packages,
        project_root,
    )

    assert path_file == site_packages / "htfa-project-root.pth"
    assert path_file.read_text(encoding="utf-8") == f"{project_root.resolve()}\n"


def test_runtime_verification_rejects_user_site_visibility(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        build_portable,
        "_run_checked",
        lambda arguments, *, cwd: calls.append((arguments, cwd)),
    )

    build_portable.verify_runtime(tmp_path / "runtime.exe", project_root=tmp_path)

    import_check = " ".join(calls[0][0])
    assert "ENABLE_USER_SITE is False" in import_check
    assert "getusersitepackages() not in sys.path" in import_check
    assert f"assert {str(tmp_path.resolve())!r} in sys.path" in import_check



def test_builder_manifest_records_python_dependencies_and_ts(tmp_path):
    lock_path = tmp_path / "requirements.lock"
    lock_path.write_text("demo==1.0\n", encoding="utf-8")
    spec = {
        "python_version": "3.13.4",
        "platform": "win_amd64",
        "archive_sha256": "a" * 64,
        "pip_version": "26.1.2",
        "pip_wheel_sha256": "c" * 64,
    }

    manifest = build_portable.build_manifest(
        spec,
        lock_path,
        ts_commit="b" * 40,
        built_at="2026-08-11T00:00:00+00:00",
    )

    assert manifest["python"] == {
        "python_version": "3.13.4",
        "platform": "win_amd64",
        "archive_sha256": "a" * 64,
    }
    assert manifest["dependency_lock"]["sha256"] == hashlib.sha256(
        lock_path.read_bytes()
    ).hexdigest()
    assert manifest["pip"] == {
        "version": "26.1.2",
        "wheel_sha256": "c" * 64,
    }
    assert manifest["ts_commit"] == "b" * 40
    assert manifest["built_at"] == "2026-08-11T00:00:00+00:00"
