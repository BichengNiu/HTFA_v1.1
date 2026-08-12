from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_OPERATIONAL_FILES = (
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "CLAUDE.md",
    PROJECT_ROOT / "docs" / "ts-runtime.md",
    PROJECT_ROOT / "data" / "CBUAE" / "README.md",
    PROJECT_ROOT / "tooling" / "docker" / "Dockerfile",
    PROJECT_ROOT / "scripts" / "windows" / "start.bat",
    PROJECT_ROOT / "scripts" / "windows" / "setup_runtime.bat",
)


def test_current_workflows_use_only_the_unified_runtime():
    legacy_venv_command = ".venv" + "\\Scripts\\python"
    legacy_lock_name = "requirements-win-" + "py313"
    for path in CURRENT_OPERATIONAL_FILES:
        text = path.read_text(encoding="utf-8")
        assert legacy_venv_command not in text, path
        assert legacy_lock_name not in text, path


def test_docker_uses_python_3134_and_the_exact_shared_lock():
    docker = (PROJECT_ROOT / "tooling" / "docker" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "FROM python:3.13.4-slim" in docker
    assert "COPY tooling/requirements/requirements-py313.lock" in docker
    assert "pip install --no-cache-dir -r requirements-py313.lock" in docker
    assert "requirements.txt" not in docker


def test_relocated_launchers_return_to_the_repository_root():
    for relative_path in (
        Path("scripts/windows/start.bat"),
        Path("scripts/windows/setup_runtime.bat"),
    ):
        content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert 'cd /d "%~dp0..\\.."' in content, relative_path


def test_relocated_compose_keeps_repository_root_as_context():
    content = (PROJECT_ROOT / "tooling" / "docker" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert "context: ../.." in content
    assert "dockerfile: tooling/docker/Dockerfile" in content
    assert "../../data:/app/data" in content
    assert "../../logs:/app/logs" in content
    assert "../../config:/app/config" in content


def test_pytest_excludes_generated_runtime_and_build_trees():
    pytest_config = (PROJECT_ROOT / "tooling" / "pytest.ini").read_text(
        encoding="utf-8"
    )
    no_recurse_line = next(
        line
        for line in pytest_config.splitlines()
        if line.strip().startswith("norecursedirs")
    )

    assert "runtime" in no_recurse_line.split()
    assert "build" in no_recurse_line.split()
    assert "dist" in no_recurse_line.split()
    assert "testpaths = ../tests" in pytest_config
    assert "pythonpath = .." in pytest_config
