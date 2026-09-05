# SARIMAX Preview Behavior Gap Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the three SARIMAX data-preview chart settings behave as configured: canvas size is preserved, legend title/column settings work for every selectable legend location, and `markersize=0` never creates implicit markers.

**Architecture:** Keep Ts as the plotting engine and make the smallest changes in the HTFA adapter. The adapter will stop overwriting the figure size, forward legend metadata through the Ts call, and remove the post-render sparse-marker mutation. Regression tests will assert the adapter call contract and the resulting legend/marker behavior.

**Tech Stack:** Python, Streamlit component adapter, Matplotlib, Ts.TsPlots, pytest.

---

### Task 1: Add regression tests for the three failures

**Files:**
- Modify: `tests/ui_shared/data_overview/test_chart_panel.py`
- Test target: `htfa/ui_shared/data_overview/ui/chart_panel.py`

**Steps:**

1. Add a patched-`plot_series` test that captures keyword arguments and asserts `figsize=(6, 4)` remains the final figure size after `draw_series_plot`.
2. Add a test that calls the adapter with `legend_loc="upper left"`, `legend_title="变量"`, and `legend_cols=2`; assert these values reach `plot_series`.
3. Replace the sparse-marker expectation with a test that verifies no extra marker line is added when `marker_size=0`.
4. Run the focused tests and confirm they fail against the current implementation.

### Task 2: Apply the minimal adapter fix

**Files:**
- Modify: `htfa/ui_shared/data_overview/ui/chart_panel.py`

**Steps:**

1. Pass `legend_title` and `legend_cols` directly into `Ts.TsPlots.plot_series`.
2. Remove the `_add_sparse_series_markers` post-processing call and its now-unneeded helper/constants/imports.
3. Remove the unconditional `fig.set_size_inches(PREVIEW_FIGSIZE)` override; preserve the `figsize` supplied to Ts, with the caller-level default already provided by `build_chart_options`.
4. Keep the existing Streamlit rendering and date compatibility behavior unchanged.

### Task 3: Validate the repair

**Commands:**

```powershell
D:\HTFA_v1.1\runtime\python.exe -m pytest -c tooling\pytest.ini tests\ui_shared\data_overview -q
D:\HTFA_v1.1\runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
```

**Expected:** Component tests pass, SARIMAX UI/boundary tests pass, and the final diff contains only the focused adapter/test/plan changes on top of the pre-existing dirty worktree.
