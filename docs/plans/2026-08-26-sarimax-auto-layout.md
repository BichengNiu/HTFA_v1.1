# SARIMAX Auto-Order Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the SARIMAX automatic-order controls compact with six range sliders on the left, model settings on the right, and post-fit multi-criterion model selection.

**Architecture:** Keep the existing `_render_auto_config()` data flow and model configuration contract compatible. Render six integer range sliders in a left column and trend, seasonal period, and two constraints in a right column. Extend Ts `AutoModelResult` with a public all-criteria table, then let HTFA choose the minimum AIC/BIC/HQIC/AICC candidate after fitting without refitting.

**Tech Stack:** Streamlit, Streamlit AppTest, Python, pytest.

---

### Task 1: Add range-slider controls

**Files:**
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/training_section.py:_render_range_inputs`

**Step 1: Add stable range-slider keys**

Use the new key format:

```python
key=f"{prefix}_{name}_range"
```

**Step 2: Render one two-ended integer slider**

Inside `_render_range_inputs`, render one `container.slider(...)` with the existing SARIMAX limits and a `(low, high)` tuple. Read the old `{prefix}_{name}_min` and `{prefix}_{name}_max` session values as the first-render fallback, while preserving the same limits, defaults, integer conversion, and return value.

**Step 3: Run the existing automatic-order UI test**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py::test_auto_mode_workflow_via_ui -q
```

Expected: PASS; all six range sliders remain discoverable by their new range keys and candidate-count behavior is unchanged.

---

### Task 2: Reorganize the automatic-order sections into two columns

**Files:**
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/training_section.py:_render_auto_config`

**Step 1: Put all six range sliders in the left column**

Use two three-column rows for `p/d/q` and `P/D/Q`, calling `_render_range_inputs` once per slider.

**Step 2: Put all model settings in the right column**

Render trend, `s（季节周期）`, stationarity, and invertibility in the right column. Remove the pre-fit criterion selector and use an internal compatible default for the Ts search. Preserve the existing defaults and add range/selection keys to the persistent widget registry.

**Step 3: Preserve model construction and warnings**

Leave `AutoSARIMAXConfig`, `candidate_count()`, the 200-combination warning, and all return paths unchanged.

---

### Task 3: Expose all candidate criteria in Ts

**Files:**
- Modify: `D:/Ts/TsModels/_auto.py`
- Modify: `D:/Ts/TsModels/README.md`
- Test: `D:/Ts/TsModels/tests/test_auto.py`

Add the public `AutoModelResult.criterion_table` property with one row per successful candidate and columns for `order`, optional `seasonal_order`, `aic`, `bic`, `hqic`, and `aicc`. Keep the existing single-criterion selection behavior backward compatible. Commit and push the canonical Ts change on `main`, then copy `_auto.py` into the HTFA runtime and verify SHA-256 equality.

### Task 4: Build the HTFA table and post-fit selection

**Files:**
- Modify: `dashboard/models/SARIMAX/core/modeling.py`
- Modify: `dashboard/models/SARIMAX/core/__init__.py`
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/training_section.py`
- Modify: `dashboard/models/SARIMAX/ui/state.py`
- Test: `tests/models/test_sarimax_modeling.py`

Build a DataFrame with columns `模型`, `AIC`, `BIC`, `HQIC`, `AICC`; add a pure selector that wraps the selected candidate as `best_result` without refitting; show the table before a post-fit criterion selector; invalidate only diagnostics and forecasts when the selected criterion changes.

### Task 5: Verify UI regression boundaries

**Files:**
- Test: `tests/models/test_sarimax_ui_flow.py::test_auto_mode_workflow_via_ui`
- Test: `tests/models/test_sarimax_ui_flow.py::test_rdl_manual_and_auto_workflows_via_ui`

**Step 1: Run focused automatic-order workflow tests**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py::test_auto_mode_workflow_via_ui tests\models\test_sarimax_ui_flow.py::test_rdl_manual_and_auto_workflows_via_ui -q
```

Expected: PASS; SARIMAX and RDL automatic error-order controls still render and fit.

**Step 2: Run the SARIMAX UI and boundary suite**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
```

Expected: all tests pass; only existing numerical/statistics warnings may remain.

**Step 3: Check the diff**

```powershell
git diff --check
```

Expected: no whitespace errors. Do not stage or modify unrelated dirty-worktree files.
