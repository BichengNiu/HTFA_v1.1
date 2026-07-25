# Stationarity Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single-table, single-variable stationarity workflow that uses the `Ts` package for summaries, plots, transformations, and selectable tests.

**Architecture:** Keep workbook parsing in `dashboard.explore.core`, pure statistical operations in `dashboard.explore.analysis`, and Streamlit rendering/state transitions in `dashboard.explore.ui`. The UI owns only user interaction; every transformation and statistical decision is exposed through testable analysis functions.

**Tech Stack:** Python 3.11, Streamlit, pandas, matplotlib, pytest, `Ts` (`TimeSeriesSummary`, `TsPlots`, `difference`, `TsTests`)

---

### Task 1: Specify transformation and diagnostic contracts

**Files:**
- Modify: `tests/explore/test_stationarity_analysis.py`
- Modify: `dashboard/explore/analysis/stationarity.py`

**Step 1: Write failing tests**

Add parameterized tests for first difference, second difference, year-over-year difference, and the three log-difference variants. Add tests proving that non-positive log inputs fail explicitly and that diagnostic helpers call `Ts.TimeSeriesSummary.summary(plot=False)` and `TsPlots`.

**Step 2: Run tests to verify failure**

Run: `python -m pytest tests/explore/test_stationarity_analysis.py -p no:cacheprovider -q`

Expected: new tests fail because the selected-series transformation and diagnostic APIs do not exist.

**Step 3: Implement the minimal analysis APIs**

Create typed transformation metadata, frequency-aware year-over-year lag resolution, summary generation, and plotting helpers. Drop missing values only for ACF/PACF and tests, while preserving missing values in the level plot and summary.

**Step 4: Run tests**

Run: `python -m pytest tests/explore/test_stationarity_analysis.py -p no:cacheprovider -q`

Expected: all analysis tests pass.

### Task 2: Add selectable Ts stationarity tests

**Files:**
- Modify: `tests/explore/test_stationarity_analysis.py`
- Modify: `dashboard/explore/analysis/stationarity.py`

**Step 1: Write failing tests**

Cover ADF, KPSS, Phillips-Perron, and Zivot-Andrews. Verify their opposite null hypotheses, alpha-aware decisions, critical-value fallback, break-date reporting, and per-test error rows.

**Step 2: Run tests to verify failure**

Run: `python -m pytest tests/explore/test_stationarity_analysis.py -p no:cacheprovider -q`

Expected: failures for the missing multi-test runner.

**Step 3: Implement the runner**

Return one normalized result row per requested test with test name, null hypothesis, statistic, p-value, lags, observations, critical value, decision, interpretation, break date, and error.

**Step 4: Run tests**

Run: `python -m pytest tests/explore/test_stationarity_analysis.py -p no:cacheprovider -q`

Expected: all analysis tests pass.

### Task 3: Replace the batch UI with the confirmed workflow

**Files:**
- Modify: `dashboard/explore/ui/stationarity.py`
- Create: `tests/explore/test_stationarity_ui.py`

**Step 1: Write failing state tests**

Verify numeric-variable selection, result invalidation when file/table/variable/transformation changes, and dynamic lag bounds.

**Step 2: Run tests to verify failure**

Run: `python -m pytest tests/explore/test_stationarity_ui.py -p no:cacheprovider -q`

Expected: failures for the new state and lag helpers.

**Step 3: Implement the three-section interface**

Render data/table/variable selection; automatic original-series diagnostics; optional transformation and processed diagnostics; and selectable tests for the original or processed series.

**Step 4: Run focused UI tests**

Run: `python -m pytest tests/explore/test_stationarity_ui.py -p no:cacheprovider -q`

Expected: all UI helper tests pass.

### Task 4: Align public APIs and the deployable Ts version

**Files:**
- Modify: `dashboard/explore/analysis/__init__.py`
- Modify: `dashboard/explore/__init__.py`
- Modify: `requirements.txt`

**Step 1: Update exports**

Export only the new supported stationarity APIs plus compatibility wrappers still used elsewhere in the repository.

**Step 2: Align the dependency**

Pin `Ts` to the same verified commit used by local development and confirm that all required public symbols exist.

**Step 3: Verify imports**

Run: `python -c "from dashboard.explore.analysis.stationarity import TRANSFORMATIONS, run_selected_stationarity_tests; print('import-ok')"`

Expected: `import-ok`.

### Task 5: Regression and runtime validation

**Files:**
- Verify: `app.py`
- Verify: `dashboard/`
- Verify: `tests/`

**Step 1: Run focused tests**

Run: `python -m pytest tests/explore -p no:cacheprovider -q`

Expected: all explore tests pass.

**Step 2: Run the full suite**

Run: `python -m pytest -p no:cacheprovider -q`

Expected: all repository tests pass.

**Step 3: Compile**

Run: `python -m compileall app.py dashboard`

Expected: exit code 0.

**Step 4: Smoke-test Streamlit**

Start the app, upload the representative workbook under `data/`, choose a frequency table and variable, inspect original and transformed diagnostics, and run all four tests against both sources.

Expected: no uncaught exception, no stale result after selection changes, and all figures/results render with visible source and method labels.
