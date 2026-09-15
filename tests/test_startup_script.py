from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROL_SCRIPT = PROJECT_ROOT / "htfa.ps1"
MOUSE_LAUNCHER = PROJECT_ROOT / "htfa.bat"


def test_startup_updates_clean_main_before_launching_htfa():
    source = CONTROL_SCRIPT.read_text(encoding="utf-8")

    assert "branch --show-current" in source
    assert "status --porcelain" in source
    assert "pull --ff-only origin main" in source
    assert source.index("pull --ff-only origin main") < source.index(
        'Start-Process -FilePath $RuntimePython'
    )


def test_startup_does_not_pull_when_worktree_is_dirty_or_branch_is_not_main():
    source = CONTROL_SCRIPT.read_text(encoding="utf-8")

    assert '$branch -ine "main"' in source
    assert '$status.Count -gt 0' in source
    assert "skipping the HTFA update" in source


def test_startup_uses_the_linked_browser_orchestrator():
    source = CONTROL_SCRIPT.read_text(encoding="utf-8")

    assert "--app=http://127.0.0.1:$Port" in source
    assert "--user-data-dir=$sessionBrowserDirectory" in source
    assert "Get-LauncherProcessId" in source
    assert "Get-BrowserSessionProcessIds" in source
    assert "launcher_closed" in source
    assert "browser_closed" in source


def test_root_control_script_exposes_start_stop_and_runtime_setup():
    source = CONTROL_SCRIPT.read_text(encoding="utf-8")

    assert 'ValidateSet("Start", "Stop", "SetupRuntime", "Watch")' in source
    assert '"Stop" { exit (Invoke-Stop) }' in source
    assert '"SetupRuntime" { exit (Invoke-SetupRuntime) }' in source
    assert not (PROJECT_ROOT / "scripts" / "start.bat").exists()
    assert not (PROJECT_ROOT / "scripts" / "stop.bat").exists()
    assert not (PROJECT_ROOT / "scripts" / "run_htfa.ps1").exists()


def test_root_mouse_launcher_delegates_to_unified_control_script():
    source = MOUSE_LAUNCHER.read_text(encoding="utf-8")

    assert 'if /I "%~1"=="stop" goto :stop' in source
    assert 'if /I "%~1"=="setup-runtime" goto :setup_runtime' in source
    assert '"%CD%\\htfa.ps1" -Command Start' in source
    assert '"%CD%\\htfa.ps1" -Command Stop' in source
