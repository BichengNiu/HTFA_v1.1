# Unified Python Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `runtime/python.exe` and its single `site-packages` tree the only Python environment used for HTFA development, tests, startup, Windows release, and exact Docker dependency versions.

**Architecture:** A PowerShell bootstrapper creates and validates `build/runtime-candidate` from pinned CPython and pip artifacts, then swaps it into `runtime` only after all checks pass. The candidate installs one exact Python 3.13 lock containing application and development tools; every normal command uses `runtime/python.exe`, while PowerShell remains the only bootstrap prerequisite.

**Tech Stack:** CPython 3.13.4 embeddable x64, PowerShell, pip 26.1.2 wheel bootstrap, pytest 9.0.2, Streamlit, Docker, Windows batch

---

### Task 1: Define the single exact dependency contract

**Files:**
- Rename: `requirements-win-py313.lock` to `requirements-py313.lock`
- Modify: `requirements.txt`
- Modify: `scripts/portable_runtime.json`
- Modify: `tests/test_portable_build.py`

**Step 1: Write failing dependency-contract tests**

Update `tests/test_portable_build.py` so the lock test reads
`requirements-py313.lock` and asserts these exact development entries:

```python
assert "pip==26.1.2" in requirements
assert "pytest==9.0.2" in requirements
assert "iniconfig==2.3.0" in requirements
assert "pluggy==1.6.0" in requirements
assert "pygments==2.20.0" in requirements
```

Extend the portable-spec expectation with:

```python
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
```

**Step 2: Run the focused tests and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_portable_build.py -q
```

Expected: failure because the renamed lock and pip specification fields do not
exist. This is the final planned use of `.venv` for TDD before the candidate
runtime contains pytest.

**Step 3: Update the dependency files**

- Rename the lock to `requirements-py313.lock`.
- Change its header to state that all CPython 3.13 environments use it.
- Add the five exact entries above in alphabetical order.
- Add `pip>=26.1,<27` and `pytest>=9.0,<10` to `requirements.txt` under a
  development-tool section.
- Add the three pip fields to `scripts/portable_runtime.json`.

Keep `requirements.txt` as supported ranges and use only the lock for actual
installation.

**Step 4: Run tests and inspect the lock**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_portable_build.py -q
rg -n "^(pip|pytest|iniconfig|pluggy|pygments)==" requirements-py313.lock
```

Expected: focused tests pass; every required tool has exactly one pin.

**Step 5: Commit**

```powershell
git add -- requirements.txt requirements-py313.lock scripts/portable_runtime.json tests/test_portable_build.py
git commit -m "统一 Python 依赖锁"
```

### Task 2: Refactor the Python builder around a candidate runtime

**Files:**
- Modify: `scripts/build_portable.py`
- Modify: `tests/test_portable_build.py`

**Step 1: Write failing candidate-builder tests**

Add tests for these contracts:

```python
def test_builder_targets_candidate_not_active_runtime():
    assert build_portable.CANDIDATE_ROOT == PROJECT_ROOT / "build" / "runtime-candidate"


def test_pip_bootstrap_runs_from_the_pinned_wheel(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        build_portable,
        "_run_checked",
        lambda arguments, *, cwd: calls.append((arguments, cwd)),
    )
    build_portable.install_locked_dependencies(
        tmp_path / "python.exe",
        tmp_path / "pip.whl",
        tmp_path / "requirements.lock",
        cwd=tmp_path,
    )
    arguments = calls[0][0]
    assert arguments[:4] == [str(tmp_path / "python.exe"), "-I", "-B", "-c"]
    assert str(tmp_path / "pip.whl") in arguments
    assert "--no-compile" in arguments


def test_runtime_verification_checks_pip_pytest_and_imports(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        build_portable,
        "_run_checked",
        lambda arguments, *, cwd: calls.append(arguments),
    )
    build_portable.verify_runtime(tmp_path / "python.exe", project_root=tmp_path)
    joined = [" ".join(call) for call in calls]
    assert any("-m pip check" in call for call in joined)
    assert any("-m pytest --version" in call for call in joined)
```

Update the manifest test to require the pip version and wheel hash.

**Step 2: Run tests and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_portable_build.py -q
```

Expected: failures for the missing candidate constant and wheel-bootstrap
signature.

**Step 3: Implement the minimal candidate builder**

Refactor `scripts/build_portable.py` to:

- use `requirements-py313.lock`;
- accept `--candidate-root` and `--pip-wheel`;
- refuse candidate paths outside the exact project
  `build/runtime-candidate` path;
- write `python313._pth` into the already extracted candidate;
- invoke pip from the verified wheel with an isolated `runpy` bootstrap:

```python
PIP_BOOTSTRAP = (
    "import runpy,sys;"
    "wheel=sys.argv.pop(1);"
    "sys.path.insert(0,wheel);"
    "sys.argv[0]='pip';"
    "runpy.run_module('pip',run_name='__main__')"
)
```

- install every lock entry with `--only-binary=:all: --no-deps --no-cache-dir
  --no-compile`;
- install pinned Ts into candidate `Lib/site-packages`;
- remove generated `Scripts/` launchers containing candidate paths;
- verify imports, `python -m pip check`, and `python -m pytest --version`;
- write a manifest containing Python, pip wheel, lock, Ts, and build timestamp;
- never delete or rename the active root `runtime`.

**Step 4: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_portable_build.py tests\test_ts_runtime.py -q
```

Expected: all focused tests pass.

**Step 5: Commit**

```powershell
git add -- scripts/build_portable.py tests/test_portable_build.py
git commit -m "重构候选运行时构建器"
```

### Task 3: Add the PowerShell bootstrap and rollback boundary

**Files:**
- Create: `setup_runtime.bat`
- Create: `scripts/bootstrap_runtime.ps1`
- Modify: `start.bat`
- Modify: `tests/test_portable_build.py`
- Modify: `tests/test_ts_launcher.py`

**Step 1: Write failing launcher and bootstrap contract tests**

Add assertions that:

- `setup_runtime.bat` calls only PowerShell and never `py`, `python`, `.venv`,
  or system pip;
- the PowerShell script names the exact `runtime`, candidate, backup, and
  download paths;
- it validates both SHA-256 values before extraction or execution;
- it runs candidate `build_portable.py`, candidate pytest, and candidate
  compileall before swapping;
- it uses literal-path moves and restores backup on final smoke failure;
- `start.bat` tells users to run `setup_runtime.bat` when runtime is absent.

**Step 2: Run tests and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_portable_build.py tests\test_ts_launcher.py -q
```

Expected: failures because the bootstrap entrypoints do not exist.

**Step 3: Implement safe external orchestration**

`setup_runtime.bat` changes to the project directory and invokes:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap_runtime.ps1
```

`scripts/bootstrap_runtime.ps1` must:

1. Resolve the project root from `$PSScriptRoot`.
2. Validate all four generated targets are exact descendants of that root.
3. Clear only `build/portable`, `build/runtime-candidate`, and stale
   `build/runtime-backup`.
4. Download the two pinned artifacts with bounded timeout behavior.
5. Compare `Get-FileHash -Algorithm SHA256` with the JSON specification.
6. Extract Python into the candidate.
7. Run candidate `scripts/build_portable.py` with explicit paths.
8. Run candidate full pytest and compileall with bytecode disabled.
9. Move current runtime to backup, candidate to runtime, and run final smoke.
10. Restore backup on a failed move or final smoke; delete backup only after
    success.

The script must return nonzero without changing active runtime on every
pre-swap failure.

**Step 4: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_portable_build.py tests\test_ts_launcher.py -q
```

Expected: all bootstrap and launcher contract tests pass.

**Step 5: Commit**

```powershell
git add -- setup_runtime.bat scripts/bootstrap_runtime.ps1 start.bat tests/test_portable_build.py tests/test_ts_launcher.py
git commit -m "增加单一运行时引导器"
```

### Task 4: Move every active workflow to the unified runtime

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/ts-runtime.md`
- Modify: `data/CBUAE/README.md`
- Modify: `Dockerfile`
- Modify: `pytest.ini`
- Create: `tests/test_runtime_workflow_contract.py`

**Step 1: Write the failing workflow-contract test**

Create a test that checks current operational files, excluding historical
plans, and asserts:

```python
for path in current_operational_files:
    text = path.read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python" not in text

docker = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
assert "FROM python:3.13.4-slim" in docker
assert "COPY requirements-py313.lock" in docker
assert "pip install --no-cache-dir -r requirements-py313.lock" in docker
```

Also assert `pytest.ini` still excludes `runtime`, `build`, and `dist` from
recursive collection.

**Step 2: Run the test and verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_runtime_workflow_contract.py -q
```

Expected: failures identifying every active `.venv` and Python 3.14 command.

**Step 3: Update workflows and documentation**

- Replace current development, test, compile, Ts install, and data-update
  commands with `runtime\python.exe ...`.
- Explain `setup_runtime.bat` as the only environment initialization command.
- State that pip and pytest intentionally ship in runtime.
- Update `AGENTS.md` cleanup protection from `.venv` to `runtime`.
- Update Docker to Python 3.13.4 and install
  `requirements-py313.lock` rather than resolving `requirements.txt`.
- Keep old dated plans as historical evidence; mark the older portable design
  superseded instead of rewriting its recorded steps.

**Step 4: Run tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_runtime_workflow_contract.py tests\test_ts_launcher.py -q
```

Expected: all workflow-contract tests pass.

**Step 5: Commit**

```powershell
git add -- AGENTS.md CLAUDE.md docs/ts-runtime.md data/CBUAE/README.md Dockerfile pytest.ini tests/test_runtime_workflow_contract.py docs/plans/2026-08-11-portable-python-runtime-design.md
git commit -m "统一开发与发布命令"
```

### Task 5: Build and validate the unified runtime end to end

**Files:**
- Generated only: `build/`
- Generated only: `runtime/`

**Step 1: Execute the real bootstrap**

Run:

```powershell
setup_runtime.bat
```

Expected: official artifact hashes match; the candidate installs all locked
wheels and pinned Ts; candidate tests pass; runtime swap succeeds.

**Step 2: Verify interpreter and development tools**

Run:

```powershell
runtime\python.exe --version
runtime\python.exe -m pip --version
runtime\python.exe -m pytest --version
runtime\python.exe -m pip check
```

Expected: Python 3.13.4, pip 26.1.2, pytest 9.0.2, and
`No broken requirements found`.

**Step 3: Run the complete repository validation**

Run:

```powershell
runtime\python.exe -B -m pytest -q
runtime\python.exe -B -m compileall app.py dashboard scripts
runtime\python.exe -B -c "import streamlit, pandas, scipy, Ts; print(Ts.__file__)"
```

Expected: complete suite passes, compileall succeeds, and Ts resolves inside
`runtime/Lib/site-packages/Ts`.

**Step 4: Validate Docker**

Run:

```powershell
docker compose build
```

Expected: Python 3.13.4 image installs the same exact lock successfully.

**Step 5: Smoke-test Streamlit**

Launch `runtime\python.exe scripts\run_htfa.py --server.headless true
--server.port=8501`, wait for `http://127.0.0.1:8501/_stcore/health` to return
HTTP 200, then terminate only the launched process.

Expected: healthy response and no `.venv` path in process diagnostics.

### Task 6: Remove the duplicate environment and finalize

**Files:**
- Remove generated local directory: `.venv/`
- Modify if needed: files found by final active-reference audit

**Step 1: Prove runtime independence before deletion**

Run the complete Task 5 validation again with commands resolved explicitly to
`runtime/python.exe`. Confirm `git status --short` contains no unexpected user
changes.

**Step 2: Resolve and remove only the project `.venv`**

Resolve `D:\sync\sync\HTFA_v1.1\.venv`, verify it is an immediate child of
the project root and is not a link, then remove only that directory. Do not
touch `runtime`, `.git`, `data`, logs, exports, or any other environment.

Expected: `.venv` no longer exists and can be recovered only by recreating it;
all supported workflows remain available through runtime.

**Step 3: Run final checks from runtime**

Run:

```powershell
runtime\python.exe -B -m pytest -q
runtime\python.exe -B -m compileall app.py dashboard scripts
runtime\python.exe -m pip check
rg -n "\.venv\\Scripts\\python|python:3\.14|requirements-win-py313" AGENTS.md CLAUDE.md Dockerfile start.bat setup_runtime.bat scripts docs/ts-runtime.md data/CBUAE/README.md tests
git diff --check
git status --short
```

Expected: tests, compilation, and pip check pass; the active-reference search
returns no matches; only intended tracked changes remain.

**Step 4: Clean generated validation artifacts**

Inspect and remove only known cache/test artifacts under the project root,
`dashboard`, `scripts`, and `tests`. Do not traverse `runtime` or `data`.

**Step 5: Commit any final scoped correction**

```powershell
git add -- <only-intended-final-files>
git commit -m "完成单一运行时迁移"
```

Skip this commit when Task 6 produces no tracked correction.
