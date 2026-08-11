import subprocess
import sys
from pathlib import Path

from scripts import run_htfa
from scripts.run_htfa import build_streamlit_argv
from scripts.ts_runtime import RuntimeSelection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_COMMIT = "1" * 40


def _write_minimal_ts(root: Path) -> Path:
    package_root = root / "Ts"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def _run_activation(root: Path) -> subprocess.CompletedProcess[str]:
    code = f"""
from pathlib import Path
from scripts.run_htfa import activate_ts_runtime
from scripts.ts_runtime import RuntimeSelection
selection = RuntimeSelection(
    root=Path({str(root)!r}),
    commit={CURRENT_COMMIT!r},
    source='downloaded',
    detail='test selection',
)
module, active = activate_ts_runtime(selection)
print(Path(module.__file__).resolve().parent)
print(active.commit)
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_activation_imports_selected_ts_without_interface_validation(tmp_path):
    runtime_root = _write_minimal_ts(tmp_path / "runtime")
    completed = _run_activation(runtime_root)
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.strip().splitlines()
    assert Path(lines[0]) == (runtime_root / "Ts").resolve()
    assert lines[1] == CURRENT_COMMIT


def test_streamlit_arguments_use_the_project_app():
    arguments = build_streamlit_argv(PROJECT_ROOT, ["--server.port=8501"])
    assert arguments == [
        "streamlit",
        "run",
        str(PROJECT_ROOT / "app.py"),
        "--server.headless",
        "false",
        "--server.port=8501",
    ]


def test_start_batch_uses_only_bundled_python():
    batch = (PROJECT_ROOT / "start.bat").read_text(encoding="utf-8")
    assert '"runtime\\python.exe" scripts\\run_htfa.py' in batch
    assert ".venv" not in batch
    system_python_lines = (
        line for line in batch.splitlines()
        if line.lstrip().lower().startswith(("py ", "python "))
    )
    assert list(system_python_lines) == []
    assert "pip" not in batch


def test_launcher_checks_for_update_once_before_streamlit(monkeypatch):
    selection = RuntimeSelection(
        root=PROJECT_ROOT,
        commit=CURRENT_COMMIT,
        source="installed",
        detail="test",
    )
    calls = {"prepare": 0, "activate": 0, "streamlit": 0}

    def prepare(**kwargs):
        calls["prepare"] += 1
        assert kwargs == {"project_root": PROJECT_ROOT}
        return selection

    def activate(selected):
        calls["activate"] += 1
        assert selected is selection
        return object(), selection

    def streamlit_main():
        calls["streamlit"] += 1
        return 0

    monkeypatch.setattr(run_htfa, "activate_ts_runtime", activate)
    result = run_htfa.main(
        ["--server.port=8501"],
        preparer=prepare,
        streamlit_main=streamlit_main,
    )
    assert result == 0
    assert calls == {"prepare": 1, "activate": 1, "streamlit": 1}
