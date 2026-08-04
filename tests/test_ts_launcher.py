import shutil
import subprocess
import sys
from pathlib import Path

from scripts import run_htfa
from scripts.run_htfa import build_streamlit_argv
from scripts.ts_runtime import RuntimeSelection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDORED_COMMIT = "bec57a2610b38be3a8f78071d7e03850b53ca25e"


def _copy_runtime(destination: Path) -> Path:
    runtime_root = destination / "runtime"
    shutil.copytree(
        PROJECT_ROOT / "Ts",
        runtime_root / "Ts",
        ignore=shutil.ignore_patterns("__pycache__", "VENDORED.*"),
    )
    return runtime_root


def _run_activation(root: Path, commit: str) -> subprocess.CompletedProcess[str]:
    code = f"""
from pathlib import Path
from scripts.run_htfa import activate_ts_runtime
from scripts.ts_runtime import RuntimeSelection
selection = RuntimeSelection(
    root=Path({str(root)!r}),
    commit={commit!r},
    source='cached',
    detail='test selection',
)
module, active = activate_ts_runtime(selection, project_root=Path({str(PROJECT_ROOT)!r}))
print(Path(module.__file__).resolve().parent)
print(active.source)
print(active.commit)
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_activate_ts_runtime_prefers_valid_selected_version(tmp_path):
    runtime_root = _copy_runtime(tmp_path)

    completed = _run_activation(runtime_root, "1" * 40)

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.strip().splitlines()
    assert Path(lines[0]) == (runtime_root / "Ts").resolve()
    assert lines[1:] == ["cached", "1" * 40]


def test_activate_ts_runtime_falls_back_when_selected_version_fails(tmp_path):
    runtime_root = tmp_path / "broken"
    package_root = runtime_root / "Ts"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text(
        "raise ImportError('broken selected runtime')\n",
        encoding="utf-8",
    )

    completed = _run_activation(runtime_root, "2" * 40)

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.strip().splitlines()
    assert Path(lines[0]) == (PROJECT_ROOT / "Ts").resolve()
    assert lines[1:] == ["vendored", VENDORED_COMMIT]


def test_streamlit_arguments_use_the_project_app():
    arguments = build_streamlit_argv(
        PROJECT_ROOT,
        ["--server.port=8501"],
    )

    assert arguments == [
        "streamlit",
        "run",
        str(PROJECT_ROOT / "app.py"),
        "--server.headless",
        "false",
        "--server.port=8501",
    ]


def test_start_batch_uses_the_runtime_launcher():
    batch = (PROJECT_ROOT / "start.bat").read_text(encoding="gbk")

    assert "py scripts\\run_htfa.py --server.port=8501" in batch
    assert "py -m streamlit run app.py" not in batch


def test_launcher_checks_once_before_starting_streamlit(monkeypatch):
    selection = RuntimeSelection(
        root=PROJECT_ROOT,
        commit=VENDORED_COMMIT,
        source="vendored",
        detail="test",
    )
    calls = {"prepare": 0, "streamlit": 0}

    def prepare(**kwargs):
        calls["prepare"] += 1
        assert kwargs == {"project_root": PROJECT_ROOT}
        return selection

    def activate(selected, *, project_root):
        assert selected is selection
        assert project_root == PROJECT_ROOT
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
    assert calls == {"prepare": 1, "streamlit": 1}
