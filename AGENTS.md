# Repository Guidelines

## 语言规则（Language rule）

- **永远用中文回复用户**（Always reply to the user in Chinese），除非用户明确另有要求。

## ⚠️ 数据变量硬性规则（Data pipeline rule，必守）

**所有新增数据变量，必须先写入 `data/UAE/uae.duckdb`，再经由 duckdb 更新到 `data/UAE/阿联酋.xlsx`。** 任何数据源禁止绕过 duckdb 直接改写 Excel 里的指标数据。

- 扩展某来源的变量：在对应 `htfa/jobs/uae_data/source_*.py` 中解析原始数据 → 入长表 → 在 `merge()` / Excel 写表 helper 中一并还原宽表。
- 已规范化（入库→合并）的做法参考 `source_cbuae.py`：`update()` 解析原文入库 `cbuae_monthly`（(period, indicator) 长表），`merge()` 从库读取并调用 `write_cbuae_sheet.ps1` 重建 `月度_CBUAE`；缺失值以 `None` 写入并留空单元格。
- 口径推算约定（CBUAE 企业部门，信贷+存款）：新格式公报（2026-05 起）不再单列 "Business & Industrial Sector" 行，只给 "Corporate / Other Financial Corporations"。经核实恒等 `商业及工业部门 = 私人企业(Corporate) − 其他金融企业(Other Financial Corporations)` 在重叠期逐月成立，故对最新公报未单列该行的期间按此式**推算补全**（`source_cbuae._extract_corporate_rows`）。存款侧取存款表「非居民」块(2) 的 Corporate 与 Other Financial 行、按同一恒等式派生（`source_cbuae._extract_nonresident_deposits`）。
- Excel 的 `指标字典` 只在 `merge()` 写表时由辅助脚本同步补录，不手工维护单个指标。

## Project layout

`app.py` is the Streamlit entry point (it injects `components/` into `sys.path` so its packages import by top-level name). Application code lives under `dashboard/`, maintenance and data-source scripts under `scripts/`, deployment configuration under `tooling/`, and reusable documentation under `docs/`. Local data belongs in `data/`; local binary references belong in `references-local/`. Do not commit credentials, databases, raw data, binary research files, logs, caches, or temporary exports.

**Independent component packages** live in `components/` — self-contained, portable Streamlit components with zero `dashboard.` imports (relative imports only; copy the folder to another project and `import <name>` works). The SARIMAX data overview is `components/data_overview/` (core/ = pure logic: constants / parsing / options / dataset / compat; ui/ = section factory + 5-tab controls + table/chart panels + builtin data source + legend). SARIMAX wires it up in `dashboard/models/SARIMAX/ui/pages/sections/__init__.py` via `create_data_overview(key_prefix="sarimax", state_namespace="model_analysis.sarimax", data_source=SharedDatasetSource(), ...)`; the adapter lives in `dashboard/models/SARIMAX/ui/overview_bridge.py`. Streamlit widget keys come from `data_overview.ui.widget_keys` and are summarized into `WIDGET_KEYS` in `dashboard/models/SARIMAX/ui/state.py`.

## Run and test

- Run HTFA with `scripts\start.bat` (project-local runtime; system Python is used only for first-time runtime setup).
- Runtime Python: `runtime\python.exe`.
- After a code change, run only the tests relevant to the changed behavior. Run the complete suite only for broad cross-module changes.
- HTFA SARIMAX regression tests (12 passed):
  `runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q`
- Component package tests (25 passed, run from `components\data_overview`):
  `runtime\python.exe -` with `sys.path.insert(0, r"C:\Users\NIU\Desktop\HTFA_v1.1\components")` then `pytest.main(["-q", "tests"])`
- UI flows are verified with `streamlit.testing.v1.AppTest` (upload sample data → navigate → expand controls → assert no exception).

## ⚠️ Mandatory workflow: plotting and model features

Any change touching plotting (chart style, axes, legend, titles, grid, multi-axis, canvas) or model features (fit, forecast, diagnostics) MUST follow this order — never edit HTFA code first:

1. **Check the Ts source package first**: `C:\Users\NIU\Desktop\Ts` (remote `github.com/BichengNiu/Ts`, branch `main`). If the capability already exists in `TsPlots/` (e.g. `plot_series`, `style.py`) use it; only add to Ts when it does not.
2. **Edit Ts first**: public functions must keep their docstring covering every signature parameter (`test_public_help_is_complete` contract); add tests for new behaviour. Run Ts tests (baseline 419 passed): `runtime\python.exe -` running `pytest.main(["-q", "tests", "TsPlots/tests"])` from `C:\Users\NIU\Desktop\Ts`.
3. **Push Ts to the remote** with a Conventional Commits message.
4. **Then edit HTFA / the component**: UI controls (`components/data_overview/ui/chart_options_tabs.py`) → `components/data_overview/core/options.py` `build_chart_options` (session_state → options) → `components/data_overview/ui/chart_panel.py` `draw_series_plot` signature and the `plot_series` call → `components/data_overview/ui/widget_keys.py` + `WIDGET_KEYS`.
5. **Sync the runtime copy**: copy changed files to `C:\Users\NIU\Desktop\HTFA_v1.1\runtime\Lib\site-packages\Ts\TsPlots\` (e.g. `ts_plot.py`, `style.py`). HTFA imports Ts from the runtime, not from the desktop source.
6. **Verify parameter consistency**: the HTFA UI layer (every dropdown/input/slider value) and the Ts `plot_series` parameters must map one-to-one — no extras, no gaps, matching defaults. Verify via static signature check (`inspect.signature`) + Chinese-option→enum mapping assertions + AppTest rendering.
7. **Remind the user to restart** `start.bat`: the Streamlit process caches modules; a page refresh is not enough.

## Known pitfalls and conventions

- **Module cache**: after Ts/dashboard changes the running process still uses old modules; kill the old process and restart `start.bat`.
- **matplotlib 3.11**: `set_title(loc=)` uses three slots (`_left_title`/`title`/`_right_title`); `get_title()` reads only the center slot. `mdates.date2num` rejects plain strings (0-d IndexError) — normalize with `pd.to_datetime` first. An undrawn `ScalarFormatter` returns empty strings — call `formatter.set_locs(ticks)` before formatting.
- **Console Chinese mojibake** is only a GBK display issue, not a logic problem.
- **Preview input formats** (SARIMAX data overview): reference lines and shade intervals accept comma-separated row numbers or dates (e.g. `1987-07`, resolved to the first data point on or after it); shade intervals are paired (start,end). Parse errors surface as `st.warning`.
- **Legend placement**: the bottom legend is drawn by HTFA (`dashboard/core/ui/utils/chart_legend.py`, `place_chart_legend_at_bottom`/`render_pyplot_figure`); Ts's native `draw_legend` is used for non-bottom locations.
- Recent Ts commits (newest first): `1d30bc4` (legend title/cols), `1273077` (centered facet panel titles), `b861525` (figsize/facet grid), `7f827b9` (manual 2nd/3rd y-axes + titles + log), `5ebe449` (grid axis/width/linestyle), `8cd6f09` (dropped freq/xtick_step), `0c7b823` (minor ticks), `ca74453` (xmin/tick and label counts).

## 推送规范（Push policy）

### 主分支提交规则（强制）

- 所有修改必须直接在本地 `main` 分支上完成并提交。
- 严禁创建、切换或使用功能分支、临时分支、修复分支或 PR 分支；不得通过分支合并回 `main`。
- 执行提交或推送前，必须确认 `git branch --show-current` 返回 `main`，并核对本地 `main` 与远端 `origin/main` 的关系。
- 后续提交统一直接推送到远端 `main`；如发现当前不在 `main`，先停止并切回 `main`，不得在其他分支继续修改。

仓库远端只应收到**正式源文件与两份数据文件**（`data/UAE/uae.duckdb` 经 Git LFS、
`data/UAE/阿联酋.xlsx`）；任何缓存、临时、中间产物、调试文件一律**不入 git、不推送**。

**绝不 add/提交/推送**（无论 .gitignore 是否已忽略，都不要碰）：

- `data/UAE/raw/**`、`data/UAE/.env`、`data/UAE/工作搜索热度.csv`、`data/UAE/uae.duckdb.wal` / `.tmp`
- `data/UAE/backups/`、`data/UAE/processed/`、`.cache/`、`.mesteel-wide-*.csv`、`.dld_indices_*.csv`
- `__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.coverage`、`htmlcov/`
- `*.pyc`、`*.pyo`、`*.tmp`、`*.temp`、`*.log`、`*.cache`、`~$*`
- 仓库根的调试残留（未跟踪的 `_*.py` / `_*.ps1` / `_*.json` / `_*.csv`）
- 用户本地数据：`data/工业/`、`data/暂存/`、`users.db`

**当用户下达「推送 / push」指令时，必须先清理再推送（强制性步骤）：**

1. 运行清理脚本：
   `powershell -NoProfile -ExecutionPolicy Bypass -File tooling\scripts\clean_temps.ps1`
   （只删除上述临时形态，**绝不**删除 `raw/`、`uae.duckdb`、`阿联酋.xlsx`、`.env`、`工业`、`暂存`、`users.db`）；
2. `git status --short` 人工复核：除本次真正要提交的正式文件外，不得出现任何缓存/临时/调试残留；
3. 再 `git add` 目标文件 → 提交 → `git push`。

**防线**：`tooling/hooks/pre-push` 已通过 `git config core.hooksPath tooling/hooks` 启用，
推送前会拦截任何暂存的临时/缓存文件；被拦截时回到第 1 步清理后重推。
`.gitignore` 已整体覆盖上述临时形态（`*.duckdb*` 全局忽略，仅 `data/UAE/uae.duckdb` 特例入库，走 LFS）。

## Code changes

Use four-space indentation and PEP 8 naming. Keep UI rendering separate from data transformation, reuse existing module utilities, and keep diffs focused. Preserve user files and unrelated worktree changes. Runtime input validation, statistical assumptions, workbook schemas, authentication, download safety, and failure rollback are product behavior and must not be removed merely to shorten the code.

## Development loop checklist

- [ ] Plotting/model change: check Ts → edit Ts → Ts tests pass → push Ts → edit component/HTFA → sync runtime
- [ ] HTFA tests pass (12) + component tests pass (25)
- [ ] UI-layer ↔ Ts-parameter consistency verified (`components/data_overview/tests/test_options.py`)
- [ ] `WIDGET_KEYS` updated
- [ ] User instructed push: run `tooling/scripts/clean_temps.ps1` → `git status` 复核 → commit → push（见「推送规范」）
- [ ] User reminded to restart `start.bat`

## Agent skills

### Issue tracker

Issues and specs are tracked in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the default five canonical triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Uses a single-context domain-doc layout. See `docs/agents/domain.md`.
