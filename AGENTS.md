# Repository Guidelines

## Project layout

`app.py` is the Streamlit entry point. Application code lives under `dashboard/`, maintenance and data-source scripts under `scripts/`, deployment configuration under `tooling/`, and reusable documentation under `docs/`. Local data belongs in `data/`; local binary references belong in `references-local/`. Do not commit credentials, databases, raw data, binary research files, logs, caches, or temporary exports.

The SARIMAX data overview and its "图形高级选项" UI live in `dashboard/models/SARIMAX/ui/overview/` (section.py orchestrates; selectors / table_panel / chart_panel / chart_options_tabs split the UI; pure parsing and options live in `dashboard/models/SARIMAX/core/overview/` — constants.py, parsing.py, options.py, all streamlit-free and unit-tested). Streamlit widget keys are registered in `dashboard/models/SARIMAX/ui/widget_keys.py` and summarized into `WIDGET_KEYS` in `dashboard/models/SARIMAX/ui/state.py` — clear keys when the widget set changes so old values are not restored.

## Run and test

- Run HTFA with `scripts\windows\start.bat` (project-local runtime; do not rely on system Python).
- Runtime Python: `runtime\python.exe`.
- After a code change, run only the tests relevant to the changed behavior. Run the complete suite only for broad cross-module changes.
- HTFA regression tests (baseline 42 passed: 12 SARIMAX flow/boundaries + 18 overview options/parsing + others):
  `runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py tests\models\test_overview_options.py tests\models\test_overview_parsing.py -q`
- UI flows are verified with `streamlit.testing.v1.AppTest` (upload sample data → navigate → expand controls → assert no exception).

## ⚠️ Mandatory workflow: plotting and model features

Any change touching plotting (chart style, axes, legend, titles, grid, multi-axis, canvas) or model features (fit, forecast, diagnostics) MUST follow this order — never edit HTFA code first:

1. **Check the Ts source package first**: `C:\Users\NIU\Desktop\Ts` (remote `github.com/BichengNiu/Ts`, branch `main`). If the capability already exists in `TsPlots/` (e.g. `plot_series`, `style.py`) use it; only add to Ts when it does not.
2. **Edit Ts first**: public functions must keep their docstring covering every signature parameter (`test_public_help_is_complete` contract); add tests for new behaviour. Run Ts tests (baseline 419 passed): `runtime\python.exe -` running `pytest.main(["-q", "tests", "TsPlots/tests"])` from `C:\Users\NIU\Desktop\Ts`.
3. **Push Ts to the remote** with a Conventional Commits message.
4. **Then edit HTFA**: UI controls (`ui/overview/chart_options_tabs.py`) → `core/overview/options.py` `build_chart_options` (session_state → options) → `ui/overview/chart_panel.py` `draw_series_plot` signature and the `plot_series` call → `ui/widget_keys.py` + `WIDGET_KEYS`.
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

## Code changes

Use four-space indentation and PEP 8 naming. Keep UI rendering separate from data transformation, reuse existing module utilities, and keep diffs focused. Preserve user files and unrelated worktree changes. Runtime input validation, statistical assumptions, workbook schemas, authentication, download safety, and failure rollback are product behavior and must not be removed merely to shorten the code.

## Development loop checklist

- [ ] Plotting/model change: check Ts → edit Ts → Ts tests pass → push Ts → edit HTFA → sync runtime
- [ ] HTFA tests pass (42 passed)
- [ ] UI-layer ↔ Ts-parameter consistency verified (`tests/models/test_overview_options.py`)
- [ ] `WIDGET_KEYS` updated
- [ ] User reminded to restart `start.bat`
