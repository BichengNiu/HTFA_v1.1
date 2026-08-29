# SARIMAX Compact Data Input Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将“动态回归模型”标签页的数据区收窄为文件上传、工作表选择、变量名行、时间列和数据开始行，然后直接进入模型训练。

**Architecture:** 在可移植的 `data_overview` 组件上增加一个默认开启的预览开关。完整数据概览实例保持现状；SARIMAX 实例关闭变量选择、表格、图表和图表高级选项，但继续复用现有 `DataSource`、文件指纹、读取设置、数据集构建和状态失效逻辑。模型训练区域继续使用当前的目标变量和外生变量选择控件。

**Tech Stack:** Python, Streamlit, Streamlit `AppTest`, pytest, pandas。

---

### Task 1: Add an optional preview-rendering switch to the reusable component

**Files:**
- Modify: `components/data_overview/ui/section.py`
- Test: `components/data_overview/tests/test_factory.py`

**Step 1: Write the failing test**

Add a component-construction test that creates `DataOverview(..., show_preview=False)` and asserts the configuration records the disabled preview mode.

**Step 2: Run the focused test**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini components\data_overview\tests\test_factory.py -p no:cacheprovider -q
```

Expected: FAIL because `DataOverview`/`DataOverviewConfig` do not yet accept `show_preview`.

**Step 3: Implement the minimal component change**

- Add `show_preview: bool = True` to `DataOverviewConfig`.
- Add the same keyword to `create_data_overview` and pass it into `DataOverview`.
- Document that `show_preview=False` still parses and stores the dataset but skips the variable selector, table panel, chart panel, and chart-options expander.
- In `render_data_overview`, return immediately after dataset construction and numeric-data validation boundary when `config.show_preview` is false; do not render preview-only widgets.
- Preserve the default `True` path byte-for-byte in behavior for Explore and Preview callers.

**Step 4: Run the focused test**

Run the same command. Expected: all component factory tests pass.

### Task 2: Wire the dynamic-regression page to compact data input

**Files:**
- Modify: `dashboard/models/SARIMAX/ui/data_input.py`
- Modify: `tests/models/test_sarimax_ui_flow.py`
- Optionally modify: `tests/models/test_sarimax_boundaries.py` if a source-boundary assertion is needed

**Step 1: Write the failing UI regression test**

Extend the SARIMAX AppTest coverage after uploading a sample CSV to assert:

- `sarimax_model_preview_variable_name_row`, `sarimax_model_preview_time_column`, and `sarimax_model_preview_data_start_row` are present.
- The training title is present immediately after the data input section.
- `sarimax_model_preview_vars` is absent.
- Preview-only table/chart widget keys such as `sarimax_model_table_filter_col`, `sarimax_model_table_view_mode`, and `sarimax_model_preview_title` are absent.
- The existing `sarimax_target_select` and `sarimax_exog_select` training controls remain available.

**Step 2: Run the focused UI test**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py -k "full_workflow_via_ui" -q
```

Expected: FAIL because the current SARIMAX data input still renders the full preview component.

**Step 3: Wire the compact mode**

Change the SARIMAX `create_data_overview(...)` call to pass `show_preview=False`. Update its renderer docstring to describe file upload and read-settings only. Keep the existing state namespace, uploader key, dataset builder, replacement callback, and widget cleanup behavior unchanged.

**Step 4: Run the focused UI test**

Run the same command. Expected: PASS with no Streamlit exception and no preview-only widgets.

### Task 3: Run regression validation and review the scoped diff

**Files:**
- No additional implementation files.

**Step 1: Run the component and SARIMAX suites**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini components\data_overview\tests -p no:cacheprovider -q
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
```

Expected: all existing component and SARIMAX tests pass; Explore and Preview callers retain their current full data-overview behavior.

**Step 2: Run static hygiene checks**

```powershell
runtime\python.exe -B -m compileall -q components\data_overview dashboard\models\SARIMAX tests\models
git diff --check
```

Expected: both commands complete without errors.

**Step 3: Review only the intended diff**

```powershell
git diff -- components/data_overview/ui/section.py components/data_overview/tests/test_factory.py dashboard/models/SARIMAX/ui/data_input.py tests/models/test_sarimax_ui_flow.py tests/models/test_sarimax_boundaries.py
```

Confirm no code under `dashboard/explore` or `dashboard/preview` was changed by this feature, and do not stage or overwrite the unrelated pre-existing worktree changes.

