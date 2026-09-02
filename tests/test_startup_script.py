from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = PROJECT_ROOT / "scripts" / "start.bat"


def test_startup_updates_clean_main_before_launching_htfa():
    source = START_SCRIPT.read_text(encoding="utf-8")

    assert "git branch --show-current" in source
    assert "git status --porcelain" in source
    assert "git pull --ff-only origin main" in source
    assert source.index("git pull --ff-only origin main") < source.index(
        'runtime\\python.exe" -B scripts\\htfa.py start'
    )


def test_startup_does_not_pull_when_worktree_is_dirty_or_branch_is_not_main():
    source = START_SCRIPT.read_text(encoding="utf-8")

    assert 'if /i not "%HTFA_BRANCH%"=="main"' in source
    assert "if defined HTFA_STATUS" in source
    assert "skipping the HTFA update" in source
