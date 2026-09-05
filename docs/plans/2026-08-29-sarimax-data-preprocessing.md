# SARIMAX Data Preprocessing Implementation Plan

> **Archive:** 历史计划，仅保留迁移前路径记录；其中路径不可作为运行入口。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在动态回归模型的训练时间范围右侧增加可多选的数据预处理参数，用于把 0 或负值按用户选择转换为缺失值，并使该选择真正影响拟合输入和结果缓存。

**Architecture:** 预处理放在 HTFA 的 `prepare_modeling_inputs` 边界，作用于已按训练时间范围裁剪、已选定的目标变量和外生变量，不修改原始 `OverviewDataset`。UI 使用现有训练状态和 `artifact_signature`，默认空选择保持现有行为；Ts 本身已有非有限值处理，但没有这两个业务语义，因此不修改 Ts 或运行时副本。

**Tech Stack:** Python, pandas, Streamlit, Streamlit `AppTest`, pytest。

---

### Task 1: Add model-input preprocessing semantics

**Files:**
- Modify: `dashboard/models/SARIMAX/core/data_loader.py`
- Test: `tests/models/test_sarimax_modeling.py`

**Step 1: Write the failing tests**

Add core tests that build a dated `OverviewDataset` containing zeros and negative values in both the target and an exogenous column, then assert:

- `preprocessing=("去零",)` converts only zeros to `NaN`.
- `preprocessing=("去负",)` converts only negative values to `NaN`.
- `preprocessing=("去零", "去负")` converts both categories to `NaN` in target and exogenous data.
- The returned index remains aligned and the source dataset frame is not mutated.
- An unknown preprocessing option raises `ValueError`.

**Step 2: Run the focused tests**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_modeling.py -k "preprocessing" -q
```

Expected: FAIL because `prepare_modeling_inputs` does not accept a preprocessing argument.

**Step 3: Implement the minimal core change**

- Define `PREPROCESSING_OPTIONS = ("去零", "去负")` in `data_loader.py`.
- Add `preprocessing: tuple[str, ...] = ()` to `prepare_modeling_inputs` and document it.
- Validate the selected options against `PREPROCESSING_OPTIONS`.
- After numeric conversion and time-range filtering, replace target/exog zeros with `NaN` when `"去零"` is selected, and values `< 0` with `NaN` when `"去负"` is selected.
- Return new Series/DataFrame objects without mutating `dataset.frame`.

**Step 4: Run the focused tests**

Run the same command. Expected: all preprocessing tests pass and existing data-loader tests remain green.

### Task 2: Add the UI control and connect it to fitting

**Files:**
- Modify: `dashboard/models/SARIMAX/ui/state.py`
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/training_section.py`
- Test: `tests/models/test_sarimax_ui_flow.py`

**Step 1: Write the failing UI regression test**

After uploading a model dataset, assert that:

- The widget `sarimax_data_preprocessing` exists to the right of the training range layout.
- Its options are exactly `去零` and `去负`, with an empty default.
- Selecting `去零` clears an existing fitted result before a new fit is run.
- The target and exogenous selectors remain available.

**Step 2: Run the focused UI test**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py -k "preprocessing" -q
```

Expected: FAIL because the widget and state key do not yet exist.

**Step 3: Implement the UI and pipeline connection**

- Add `sarimax_data_preprocessing` to `MODEL_WIDGET_KEYS` so it persists and is cleared with dataset replacement.
- Change the training control layout from four to five columns: target, exogenous variables, training range, preprocessing, and (for RDL/ARDL) target-log control.
- Render `st_obj.multiselect("数据预处理", options=("去零", "去负"), key="sarimax_data_preprocessing")` in the column immediately after the training range.
- Store the selected tuple in SARIMAX state under `data_preprocessing`; clear fit results when it changes; reset it in the dataset-replacement callback.
- Pass `preprocessing=preprocessing` into `prepare_modeling_inputs`.
- Add the selected tuple to the `artifact_signature` parameters so old fit/diagnostic/forecast artifacts cannot be reused after a preprocessing change.
- Keep the default empty selection behavior unchanged.

**Step 4: Run the focused UI test**

Run the same command. Expected: PASS with the new control, correct invalidation, and no Streamlit exception.

### Task 3: Validate all affected behavior

**Files:**
- No additional implementation files.

**Step 1: Run the affected suites**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_modeling.py tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
runtime\python.exe -B -m pytest -c tooling\pytest.ini tests\ui_shared\data_overview -p no:cacheprovider -q
```

Expected: all model/core/UI and reusable data-overview tests pass.

**Step 2: Run static checks**

```powershell
runtime\python.exe -B -m compileall -q htfa\models\univariate\sarimax tests\models
git diff --check
```

Expected: both commands complete without errors.

**Step 3: Review the scoped diff**

```powershell
git diff -- dashboard/models/SARIMAX/core/data_loader.py dashboard/models/SARIMAX/ui/state.py dashboard/models/SARIMAX/ui/pages/sections/training_section.py tests/models/test_sarimax_modeling.py tests/models/test_sarimax_ui_flow.py
```

Confirm that Ts, Explore, Preview, and the original dataset are unchanged; do not stage or overwrite unrelated pre-existing worktree changes.
