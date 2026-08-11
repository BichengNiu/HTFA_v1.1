# HTFA Windows Self-Contained Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 交付一个内置 CPython 3.13.4 和全部依赖的 Windows x64 HTFA 目录，并在每次 `start.bat` 启动时通过 HTTPS 将 Ts 更新到公开仓库 `main` 最新提交。

**Architecture:** 开发环境继续使用未提交的 `.venv`，发布产物使用官方 CPython 3.13.4 嵌入式运行时和锁定的 Windows wheel。启动器先查询公开 GitHub API；有新提交则直接下载并原子替换当前 Ts，无网络或更新失败则使用当前版本。实现删除系统 Git、多版本缓存、候选接口验证和独立进程烟测，但保留 HTTPS、ZIP 路径安全、体积限制和原子文件替换。

**Tech Stack:** CPython 3.13.4 embeddable x64、Python 标准库、pip `--python`、Streamlit、pytest、Windows Batch/PowerShell、GitHub REST/codeload HTTPS

---

## 约束和不变量

- 只在当前 `main` 分支工作，不创建功能分支。
- 不提交 `runtime/`、`build/`、`dist/`、wheel 下载目录或 `.venv/`。
- 不修改 `dashboard/`、`data/` 或 UAE 分析行为。
- Docker 运行时仍保持现状；只修正文档中“与本地一致”的错误表述。
- Ts 更新源固定为 `BichengNiu/Ts:main`；`main` HEAD 就是最新版。
- 不做候选 Ts 的接口验证、导入验证、烟测或自动回退。
- 下载失败不得改变当前 Ts；下载成功且完成安全提取后，本次启动直接使用新版本。
- 每次准备提交以及最终交付前，按 `AGENTS.md` 精确清理缓存并复查 `git status --short`。

### Task 1: Align the Windows development baseline with Python 3.13.4

**Files:**
- Modify: `.python-version:1`
- Modify: `AGENTS.md:7-12`
- Modify: `Dockerfile:3`

**Step 1: Record the current interpreter evidence**

Run:

```powershell
python --version
py -0p
```

Expected: `python --version` reports `Python 3.13.4`; `py -0p` lists the same interpreter. Do not continue with a different patch version because the portable archive is pinned to 3.13.4.

**Step 2: Rebuild only the broken project development environment**

Run:

```powershell
python -m venv --clear .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install pytest==9.0.2
```

Expected: `.venv\Scripts\python.exe --version` reports `Python 3.13.4`. This explicitly replaces the copied, unusable Python 3.14 virtual environment; do not remove any other directory.

**Step 3: Update the documented baseline**

- Set `.python-version` to `3.13.4`.
- Change the development install command in `AGENTS.md` to state Python 3.13.4.
- Keep `Dockerfile` on `python:3.14.6-slim`, but change its comment to say the container runtime is independent from the Windows portable runtime.

**Step 4: Verify the baseline**

Run:

```powershell
.venv\Scripts\python.exe -c "import sys; assert sys.version_info[:3] == (3, 13, 4); print(sys.version)"
git diff --check
```

Expected: the assertion passes and `git diff --check` prints nothing.

**Step 5: Clean and commit**

Inspect and remove only generated caches under the project root, `dashboard/`, `scripts/`, and `tests/`; never traverse `.venv/` or `data/` for cleanup.

```powershell
git add -- .python-version AGENTS.md Dockerfile
git commit -m "统一 Windows Python 3.13.4 基线"
```

### Task 2: Replace the Git/cache/validation updater with direct HTTPS replacement

**Files:**
- Modify: `scripts/ts_runtime.py:24-746`
- Modify: `scripts/install_ts.py:23-57`
- Rewrite: `tests/test_ts_runtime.py`

**Step 1: Write failing tests for the approved behavior**

Replace tests for `UpdateLock`, state files, verified versions, interface validation and smoke testing with:

```python
def test_offline_uses_current_installed_version(tmp_path): ...
def test_matching_main_head_skips_download(tmp_path): ...
def test_new_main_head_replaces_current_ts_without_smoke_test(tmp_path): ...
def test_download_failure_keeps_current_ts(tmp_path): ...
def test_head_response_requires_full_commit_sha(): ...
def test_extract_rejects_zip_path_traversal(tmp_path): ...
def test_extract_accepts_allowlisted_ts_files(tmp_path): ...
def test_install_failure_restores_previous_ts(tmp_path): ...
```

The no-smoke test must create a candidate whose `Ts/__init__.py` raises an exception and assert that installation still succeeds. This proves the approved risk boundary rather than silently restoring validation. Inject `install_root`, `head_fetcher` and `candidate_materializer` into `prepare_ts_runtime()` so tests never edit the active interpreter.

**Step 2: Run the tests and verify the intended failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ts_runtime.py -q
```

Expected: failures reference the removed cache contract or missing HTTPS materializer; collection succeeds without importing Ts.

**Step 3: Simplify the updater API**

Keep these public concepts in `scripts/ts_runtime.py`:

```python
GITHUB_API_URL = "https://api.github.com/repos/BichengNiu/Ts/commits/main"
GITHUB_ARCHIVE_URL = "https://codeload.github.com/BichengNiu/Ts/zip/{commit}"
CHECK_TIMEOUT_SECONDS = 3
DOWNLOAD_TIMEOUT_SECONDS = 30

class RuntimeUpdateError(RuntimeError): ...

@dataclass(frozen=True)
class RuntimeSelection:
    root: Path
    commit: str
    source: str
    detail: str

def fetch_head_commit(*, opener=urlopen, timeout=CHECK_TIMEOUT_SECONDS) -> str: ...
def materialize_github_runtime(commit: str, destination: Path, *, opener=urlopen) -> str: ...
def extract_runtime_archive(archive_path: Path, destination: Path) -> Path: ...
def installed_runtime_selection(root: Path | None = None) -> RuntimeSelection: ...
def install_ts_runtime(source_root: Path, *, commit: str,
                       install_root: Path | None = None) -> RuntimeSelection: ...
def prepare_ts_runtime(*, project_root: Path, install_root: Path | None = None,
                       head_fetcher=None, candidate_materializer=None) -> RuntimeSelection: ...
```

Delete `UpdateLock`, state read/write, Git subprocess helpers, cached version discovery/pruning, `smoke_test_runtime`, `REQUIRED_INTERFACES`, and all exports for them.

`fetch_head_commit()` sends a fixed User-Agent, parses GitHub JSON, and accepts only a 40-character lowercase hexadecimal SHA. `materialize_github_runtime()` streams the fixed-commit ZIP with the existing 25 MiB compressed and 50 MiB extracted limits, calculates SHA-256 for diagnostics, and calls the retained safe extractor.

`prepare_ts_runtime()` implements exactly this order:

```python
installed = installed_runtime_selection(install_root)
try:
    head = fetch_head()
except Exception as exc:
    return replace(installed, detail=f"update check failed: {exc}")
if head == installed.commit:
    return replace(installed, detail="current Ts matches main HEAD")
try:
    materialize(head, candidate_root)
    updated = install_ts_runtime(candidate_root, commit=head, install_root=install_root)
    return replace(updated, source="downloaded", detail="updated from main HEAD")
except Exception as exc:
    return replace(installed, detail=f"update failed: {exc}")
```

Do not call or recreate a smoke test between materialization and installation.

**Step 4: Make bootstrap installation targetable**

Add `--install-root PATH` to `scripts/install_ts.py`. Pass it through `install()` to `install_ts_runtime()` so the portable builder can install the pinned bootstrap Ts into `runtime/Lib/site-packages` without activating that runtime.

**Step 5: Run focused tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ts_runtime.py -q
```

Expected: all updater tests pass; no test name or implementation references cache versions, smoke tests, `UpdateLock` or system Git.

**Step 6: Install the pinned Ts and commit**

```powershell
.venv\Scripts\python.exe scripts\install_ts.py
.venv\Scripts\python.exe -c "import Ts; print(Ts.__file__)"
git add -- scripts/ts_runtime.py scripts/install_ts.py tests/test_ts_runtime.py
git commit -m "简化 Ts HTTPS 自动更新"
```

Expected: Ts imports from `.venv\Lib\site-packages\Ts`; no generated environment files are committed.

### Task 3: Make start.bat use only the bundled runtime

**Files:**
- Modify: `scripts/run_htfa.py:25-154`
- Modify: `start.bat:14-65`
- Modify: `tests/test_ts_launcher.py:1-137`

**Step 1: Rewrite launcher tests first**

Add or update:

```python
def test_start_batch_uses_only_bundled_python():
    batch = (PROJECT_ROOT / "start.bat").read_text(encoding="utf-8")
    assert '"runtime\\python.exe" scripts\\run_htfa.py' in batch
    assert ".venv" not in batch
    assert "py -" not in batch

def test_launcher_checks_for_update_once_before_streamlit(monkeypatch): ...
def test_activation_imports_selected_ts_without_interface_validation(tmp_path): ...
def test_streamlit_arguments_use_project_app(): ...
```

Remove the test requiring fallback from a broken selected Ts; automatic fallback after successful replacement is outside the approved design.

**Step 2: Verify the tests fail**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ts_launcher.py -q
```

Expected: the batch assertion fails because `start.bat` still references `.venv`.

**Step 3: Simplify run_htfa.py**

- Keep exactly one `prepare_ts_runtime(project_root=PROJECT_ROOT)` call before importing Ts and starting Streamlit.
- Remove required-interface checks and fallback-to-installed logic from `activate_ts_runtime()`.
- Retain import-path selection only so the freshly installed site-packages Ts is imported in the current process.
- Report `downloaded`, current, and offline/update-failure details accurately.
- Do not catch import failure from newly installed Ts; expose the real traceback.

**Step 4: Replace the environment section in start.bat**

Use:

```bat
if not exist "runtime\python.exe" (
    echo [ERROR] Bundled runtime\python.exe was not found.
    echo [HINT] This package is incomplete. Extract the full HTFA release again.
    goto :failed
)

"runtime\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Bundled Python cannot start. The release may be damaged.
    goto :failed
)
```

The final command is:

```bat
"runtime\python.exe" scripts\run_htfa.py --server.port=8501 %*
```

Do not create, repair or install into `.venv`; do not call pip or system `py/python/git`.

**Step 5: Run focused tests and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_ts_runtime.py tests/test_ts_launcher.py -q
git add -- scripts/run_htfa.py start.bat tests/test_ts_launcher.py
git commit -m "切换 HTFA 自包含启动器"
```

Expected: all focused tests pass and `rg -n "\.venv|py -|pip|git " start.bat` returns no matches.

### Task 4: Build the reproducible Python 3.13.4 portable package

**Files:**
- Create: `scripts/portable_runtime.json`
- Create: `requirements-win-py313.lock`
- Create: `scripts/build_portable.py`
- Create: `tests/test_portable_build.py`
- Modify: `.gitignore`

**Step 1: Add failing build-contract tests**

```python
def test_portable_spec_pins_python_3134_and_official_sha256(): ...
def test_portable_lock_contains_only_exact_pins(): ...
def test_builder_refuses_cleanup_outside_build_and_dist(tmp_path): ...
def test_builder_writes_embedded_python_path_file(tmp_path): ...
def test_builder_copies_only_release_files(tmp_path): ...
def test_builder_manifest_records_python_dependencies_and_ts(tmp_path): ...
```

Expected specification:

```json
{
  "python_version": "3.13.4",
  "platform": "win_amd64",
  "archive_url": "https://www.python.org/ftp/python/3.13.4/python-3.13.4-embed-amd64.zip",
  "archive_sha256": "514ca14ec356ecb7749a7c0a1ef1eac9fd9c67d57af4812cb1f0822b0d3a85e8"
}
```

**Step 2: Verify the new tests fail**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_portable_build.py -q
```

Expected: collection fails because `scripts.build_portable` and its specification do not exist.

**Step 3: Add the exact dependency lock**

Use only `name==version` entries and comments:

```text
altair==6.2.2
anyio==4.14.2
arch==8.0.0
attrs==26.1.0
bcrypt==5.0.0
blinker==1.9.0
certifi==2026.7.22
charset-normalizer==3.4.9
click==8.4.2
colorama==0.4.6
contourpy==1.3.3
cycler==0.12.1
dtaidistance==2.4.0
et-xmlfile==2.0.0
fonttools==4.63.0
h11==0.16.0
httptools==0.8.0
idna==3.18
itsdangerous==2.2.0
jinja2==3.1.6
joblib==1.5.3
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
kiwisolver==1.5.0
markupsafe==3.0.3
matplotlib==3.11.1
narwhals==2.24.0
numpy==2.5.2
openpyxl==3.1.5
packaging==26.3
pandas==3.0.5
patsy==1.0.2
pillow==12.3.0
plotly==6.9.0
protobuf==7.35.1
pyarrow==24.0.0
pydeck==0.9.3
pyparsing==3.3.2
pypdf==6.15.0
python-dateutil==2.9.0.post0
python-multipart==0.0.32
pytz==2026.3.post1
referencing==0.37.0
requests==2.34.2
rpds-py==2026.6.3
scikit-learn==1.9.0
scipy==1.18.0
six==1.17.0
starlette==1.3.1
statsmodels==0.14.6
streamlit==1.61.1
tenacity==9.1.4
threadpoolctl==3.6.0
toml==0.10.2
typing-extensions==4.16.0
tzdata==2026.3
urllib3==2.7.0
uvicorn==0.52.1
watchdog==6.0.0
websockets==16.1.1
xlrd==2.0.2
```

**Step 4: Implement scripts/build_portable.py**

The builder must:

1. Resolve fixed `build/portable` and `dist/HTFA-win-x64` targets.
2. Refuse cleanup unless both are strict repository children with exact expected final names.
3. Download the official Python ZIP, verify its pinned SHA-256, and extract to `runtime/`.
4. Write `runtime/python313._pth` as:

   ```text
   python313.zip
   .
   Lib
   Lib/site-packages
   import site
   ```

5. Invoke builder pip with `--python dist/.../runtime/python.exe`, `--only-binary=:all:`, `--no-deps` and the exact lock.
6. Call `scripts.install_ts.install(install_root=runtime/Lib/site-packages)` for the pinned bootstrap Ts.
7. Copy only `app.py`, `dashboard/`, `scripts/`, `data/`, `.streamlit/`, `start.bat` and the lock. Exclude tests, docs, caches, Git, venv, credentials and temporary files.
8. Write `runtime-manifest.json` with Python version/platform/archive hash, lock hash, pinned Ts commit, UTC build timestamp and copied top-level entries.
9. Use embedded Python to import `streamlit`, `pandas`, `numpy`, `scipy`, `statsmodels`, `sklearn`, `matplotlib`, `dtaidistance`, `arch` and `Ts`.

Add root-only `/build/`, `/dist/`, `/runtime/` and `/wheelhouse/` to `.gitignore`.

**Step 5: Run unit tests**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_portable_build.py -q
.venv\Scripts\python.exe -m pytest tests/test_ts_runtime.py tests/test_ts_launcher.py -q
```

Expected: all pass without leaving fixture build directories in the repository.

**Step 6: Commit**

```powershell
git add -- .gitignore requirements-win-py313.lock scripts/portable_runtime.json scripts/build_portable.py tests/test_portable_build.py
git commit -m "增加 Python 3.13.4 便携构建"
```

### Task 5: Document and run full portable acceptance

**Files:**
- Modify: `docs/ts-runtime.md`
- Test/generated only: `dist/HTFA-win-x64/`

**Step 1: Rewrite runtime documentation**

Document:

- Development `.venv` is machine-local and must never be copied; recreate with Python 3.13.4.
- Build with `.venv\Scripts\python.exe scripts\build_portable.py`.
- Copy `dist/HTFA-win-x64`; target machines run `start.bat` without Python, pip or Git.
- Every start checks public `Ts/main`, installs a different HEAD without behavior validation, and keeps current Ts only on network/download failure.
- A broken but successfully downloaded `main` can break HTFA; this risk is accepted.

**Step 2: Run full tests**

```powershell
.venv\Scripts\python.exe -m compileall app.py dashboard scripts
.venv\Scripts\python.exe -m pytest -q
```

Expected: compile succeeds and the full suite passes; record exact pass count.

**Step 3: Build the real artifact**

```powershell
.venv\Scripts\python.exe scripts\build_portable.py
```

Expected: `dist/HTFA-win-x64/runtime/python.exe` is Python 3.13.4; manifest hashes match; artifact has no `.venv`, Git, tests, caches, tokens, `.env` or source-control metadata.

**Step 4: Test relocation and offline behavior**

Copy the artifact to a temporary path containing spaces. Simulate updater HTTP failure through dependency injection; do not disconnect the machine globally.

```powershell
& '<temporary path>\runtime\python.exe' --version
& '<temporary path>\runtime\python.exe' -c "import streamlit, pandas, scipy, Ts; print(Ts.__file__)"
```

Expected: Python 3.13.4; Ts resolves strictly inside the relocated artifact; output contains no build-machine user path.

**Step 5: Test real online update**

In an isolated artifact copy, set installed metadata to an older valid commit without changing Ts code, then run against the real public repository.

Expected: one HEAD request finds current `main`; fixed-commit ZIP downloads; metadata changes to that SHA; second run skips download; no system Git, Python, pip or venv is invoked. Do not push a test commit.

**Step 6: Run Streamlit health smoke**

Start relocated `start.bat`, wait for `http://127.0.0.1:8501/_stcore/health`, assert healthy, exercise the affected startup page with representative files under `data/`, and stop only the exact process started.

Expected: healthy dashboard with no environment error or old absolute path.

**Step 7: Clean and audit**

Inspect and delete only verified caches under the root, `dashboard/`, `scripts/` and `tests/`. Do not delete `.venv`, Git, `data/`, logs or exports.

```powershell
git diff --check
git status --short
rg -n "C:\\Users\\mfa|Python314|\.venv\\Scripts\\python" start.bat scripts docs requirements-win-py313.lock
```

Expected: only intended changes; caches absent; old path/launcher references absent outside superseded historical designs.

**Step 8: Commit documentation**

```powershell
git add -- docs/ts-runtime.md
git commit -m "完善便携运行时说明"
```

Do not commit `dist/`. Report its absolute path, size, manifest hashes, test count, relocation/offline result, online update result and health-check result.

## Completion audit

- `start.bat` contains no venv, system Python, pip or Git fallback.
- Portable runtime is exactly CPython 3.13.4 Windows x64.
- Dependency lock is exact and artifact records its hash.
- Ts lookup/download uses HTTPS without credentials.
- No interface validation or smoke test runs before installing Ts.
- Network/download failures preserve and use current Ts.
- Safe extraction and atomic replacement remain enforced.
- Release relocates across users and paths without absolute references.
- Full tests, compile, online update and Streamlit health checks pass.
- Generated artifacts and caches are absent from Git status.
- No UAE logic or project data changed.

