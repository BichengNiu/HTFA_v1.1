# Vendor Ts Package Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `Ts` 固定版本源码内置到 HTFA，使本机和容器运行均不再依赖 GitHub 安装或 UAE 内置 Excel 文件。

**Architecture:** 在仓库根目录新增顶层 `Ts` Python 包，保持现有 `from Ts ...` 公共导入不变。源码固定来自上游提交 `bec57a2610b38be3a8f78071d7e03850b53ca25e`，只复制运行时 Python 源文件；HTFA 依赖文件负责声明其第三方依赖，Docker 直接复制本地包。

**Tech Stack:** Python 3.11+、Streamlit、pytest、Docker Compose、setuptools 风格 Python 包

---

### Task 1: Vendor the pinned runtime package

**Files:**
- Create: `Ts/__init__.py`
- Create: `Ts/TsMetrics/*.py`
- Create: `Ts/TsModels/*.py`
- Create: `Ts/TsPlots/*.py`
- Create: `Ts/TsSims/*.py`
- Create: `Ts/TsTests/*.py`
- Create: `Ts/TsUtils/*.py`
- Create: `Ts/VENDORED.md`

**Step 1: Verify the target does not exist**

Run: `Test-Path Ts`

Expected: `False`.

**Step 2: Copy runtime Python sources from the pinned commit**

Copy only root `__init__.py` and `.py` files under the six runtime subpackages. Exclude upstream tests, notebooks, READMEs, cache files, development configuration, and repository metadata.

Expected: the local `Ts` package contains the same runtime `.py` blob hashes as commit `bec57a2610b38be3a8f78071d7e03850b53ca25e`.

**Step 3: Record provenance**

Create `Ts/VENDORED.md` with the upstream URL, exact commit, vendoring date, included/excluded scope, dependency ownership, and a note that the upstream snapshot did not contain a license file.

**Step 4: Verify public imports**

Run:

```powershell
python -c "import Ts; from Ts import TimeSeriesSummary, difference; from Ts.TsPlots import plot_acf, plot_pacf, plot_series; from Ts.TsTests import ADFTest, KPSSTest, PhillipsPerronTest, ZivotAndrewsTest; print(Ts.__file__)"
```

Expected: import succeeds and `Ts.__file__` resolves inside this repository.

### Task 2: Make dependencies and Docker self-contained

**Files:**
- Modify: `requirements.txt`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`

**Step 1: Replace the remote Ts dependency**

Remove:

```text
Ts @ git+https://github.com/BichengNiu/Ts.git@bec57a2610b38be3a8f78071d7e03850b53ca25e
```

Add the missing hard dependency:

```text
arch>=7.0,<9.0
```

Raise the existing statsmodels lower bound to the vendored package contract:

```text
statsmodels>=0.14.5,<0.15
```

**Step 2: Simplify Docker dependency installation**

Remove the Git package, BuildKit GitHub secret mount, temporary Git credential rewrite, and credential cleanup. Keep a direct `pip install --no-cache-dir -r requirements.txt` step.

**Step 3: Copy the vendored package into the image**

Add:

```dockerfile
COPY Ts/ ./Ts/
```

**Step 4: Remove the obsolete Compose build secret**

Remove the service-level `build.secrets` entry and top-level `secrets.github_token` definition. Do not modify data volumes or runtime environment variables.

### Task 3: Add the vendored-package regression contract

**Files:**
- Create: `tests/test_vendored_ts.py`

**Step 1: Write the package-location test**

```python
from pathlib import Path

import Ts


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ts_import_resolves_to_vendored_package():
    assert Path(Ts.__file__).resolve().parent == (PROJECT_ROOT / "Ts").resolve()
```

**Step 2: Write the HTFA public-interface test**

```python
def test_vendored_ts_exposes_htfa_interfaces():
    from Ts import TimeSeriesSummary, difference
    from Ts.TsPlots import plot_acf, plot_pacf, plot_series
    from Ts.TsTests import (
        ADFTest,
        KPSSTest,
        PhillipsPerronTest,
        ZivotAndrewsTest,
    )

    assert all(
        callable(item)
        for item in (
            TimeSeriesSummary,
            difference,
            plot_acf,
            plot_pacf,
            plot_series,
            ADFTest,
            KPSSTest,
            PhillipsPerronTest,
            ZivotAndrewsTest,
        )
    )
```

**Step 3: Write the dependency-source test**

```python
def test_requirements_do_not_install_ts_from_git():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "BichengNiu/Ts" not in requirements
    assert "git+" not in requirements
```

**Step 4: Run the focused contract**

Run: `python -m pytest tests/test_vendored_ts.py -q`

Expected: `3 passed`.

### Task 4: Verify without relying on a bundled UAE workbook

**Files:**
- Verify only; do not modify `data/阿联酋.xlsx` or UAE application modules.

**Step 1: Compile application and vendored package**

Run: `python -m compileall app.py dashboard Ts`

Expected: exit code 0.

**Step 2: Run Ts-dependent Explore regressions**

Run:

```powershell
python -m pytest tests/test_vendored_ts.py tests/explore/test_stationarity_analysis.py tests/explore/test_structural_break_analysis.py tests/explore/test_stationarity_streamlit.py tests/explore/test_structural_break_streamlit.py -q
```

Expected: all tests pass. Tests use generated/in-memory data and do not read `data/阿联酋.xlsx`.

**Step 3: Validate Compose configuration**

Run: `docker compose config --quiet`

Expected: exit code 0 without requiring `GITHUB_TOKEN`.

**Step 4: Validate the clean installation contract**

Create a temporary virtual environment outside the repository, install `requirements.txt`, and run the public import check with the repository root on `sys.path`.

Expected: installation and imports succeed without cloning the Ts repository.

**Step 5: Attempt the container build when the daemon is available**

Run: `docker compose build htfa-app`

Expected: image builds without GitHub credentials. If Docker Desktop remains stopped, report this environmental limitation separately; do not weaken other validation.
