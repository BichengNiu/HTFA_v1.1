# Dynamic Regression Training Range Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an inclusive date-range picker beside the target and exogenous-variable selectors, so Dynamic Regression fits only the selected dated observations.

**Architecture:** Keep the filter in the SARIMAX core data-preparation boundary: the UI passes an optional `(start, end)` pair to `prepare_modeling_inputs`, which filters the common target/exogenous frame before fitting. The UI owns widget state and fit-result invalidation; Ts model APIs and all three model-family semantics remain unchanged.

**Tech Stack:** Python, pandas, Streamlit `date_input`, HTFA namespaced session state, pytest, Streamlit AppTest.

---

### Task 1: Define and test core sample filtering

**Files:**

- Modify: `dashboard/models/SARIMAX/core/data_loader.py:116-157`
- Test: `tests/models/test_sarimax_modeling.py:105-139`

**Step 1: Write the failing test**

Add a dated-data test calling:

```python
series, exog, index = prepare_modeling_inputs(
    dataset, "value", ("x",),
    time_range=(pd.Timestamp("2024-02-01"), pd.Timestamp("2024-03-01")),
)
assert index.tolist() == [pd.Timestamp("2024-02-01"), pd.Timestamp("2024-03-01")]
assert series.index.equals(index)
assert exog is not None and exog.index.equals(index)
```

Also add validation tests: reject a range when the dataset has no time column and reject an inverted range with clear Chinese messages.

**Step 2: Run test to verify it fails**

Run: `runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_modeling.py -q`

Expected: FAIL because `time_range` is not an accepted parameter.

**Step 3: Write minimal implementation**

Extend `prepare_modeling_inputs` with an optional `time_range: tuple[pd.Timestamp, pd.Timestamp] | None = None`. After building and validating the `DatetimeIndex`, apply the inclusive mask `start <= index <= end` to `base`; return the filtered target, exogenous frame, and index. Preserve current full-sample and `RangeIndex` behavior when `time_range is None`.

**Step 4: Run test to verify it passes**

Run: `runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_modeling.py -q`

Expected: PASS.

### Task 2: Render the training-range control and invalidate stale results

**Files:**

- Modify: `dashboard/models/SARIMAX/ui/pages/sections/training_section.py:68-157`
- Modify: `dashboard/models/SARIMAX/ui/state.py:20-122,157-165`

**Step 1: Write the failing page-flow test**

In `tests/models/test_sarimax_ui_flow.py`, upload `_dynamic_sample_csv()` and assert a `sarimax_training_time_range` date-range widget appears. Set it to a strict subset, run the page, fit, then change the range and assert the former result metrics are absent until refitted.

**Step 2: Run test to verify it fails**

Run: `runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py -q`

Expected: FAIL because the training widget and state invalidation do not exist.

**Step 3: Write minimal implementation**

Change `select_columns = st_obj.columns(2)` to three columns. In the third column, when `dataset.time_column` exists, render:

```python
time_range = st_obj.date_input(
    "训练时间范围",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=date_max,
    key="sarimax_training_time_range",
    help="仅使用该闭区间内的观测值拟合模型。",
)
```

Normalize the chosen dates to `pd.Timestamp`, persist the tuple in the SARIMAX namespace, clear fit results whenever it changes, and pass it to `prepare_modeling_inputs`. Include the normalized range in `fit_signature`, add the widget key to `MODEL_WIDGET_KEYS`, and reset the namespaced range in `clear_dataset_state` so a new upload cannot inherit stale dates. If Streamlit yields an incomplete range, display a user-readable warning and do not fit.

**Step 4: Run test to verify it passes**

Run: `runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py -q`

Expected: PASS, including existing SARIMAX/RDL/ARDL page flows.

### Task 3: Verify regression boundaries

**Files:**

- Test: `tests/models/test_sarimax_modeling.py`
- Test: `tests/models/test_sarimax_ui_flow.py`

**Step 1: Run focused suites**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_modeling.py tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
```

Expected: all selected tests pass; filtering uses one aligned index for target and exogenous inputs, existing no-date uploads retain `RangeIndex`, and changing the range never leaves an old fit active.

**Step 2: Inspect the working-tree diff**

Run: `git diff --check` and `git diff -- dashboard/models/SARIMAX/core/data_loader.py dashboard/models/SARIMAX/ui/pages/sections/training_section.py dashboard/models/SARIMAX/ui/state.py tests/models/test_sarimax_modeling.py tests/models/test_sarimax_ui_flow.py`

Expected: only focused source/test changes; no Ts or runtime-package copies are needed because this only selects the input sample before the existing public Ts calls.

**Step 3: Commit only if requested**

Run: `git add` for the approved source and test files, then `git commit -m "feat: add dynamic regression training range"`.

Expected: one focused commit on `main`; do not push unless separately instructed.
