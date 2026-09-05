# RDL Intervention Time Controls Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the RDL intervention date controls visually match the three shock semantics: a point for `pulse`, a red tail for `step`, and an unchanged red interval for `temporary`, while displaying the latter as “区间冲击（interval）”.

**Architecture:** Keep the existing `RDLInterventionConfig`, Ts `EventSpec`, and model path generation unchanged. Adjust only the RDL UI control construction, timestamp display formatter, and declared widget state keys: `pulse` will use a single-date select box, `step` will use a range slider whose upper endpoint is the last model date, and `temporary` will retain the current inclusive range slider. The widgets will keep full `pd.Timestamp` values for exact matching, while their labels will show only the meaningful timestamp precision. Translate each UI result back to the existing start/end configuration without changing the internal `pulse`/`step`/`temporary` values.

**Tech Stack:** Python, Streamlit 1.61.1, Streamlit `AppTest`, pytest.

---

### Task 1: Update the RDL UI contract tests

**Files:**
- Modify: `tests/models/test_sarimax_ui_flow.py:806-895`

**Step 1: Write the failing test assertions**

- Assert the default `pulse` control is a single-date `selectbox` with a dedicated key, so it cannot render a selected interval.
- Assert switching to `step` renders a `select_slider` range whose value ends at the last model date.
- Assert changing the step range cannot move its upper endpoint away from the last model date.
- Assert switching to `temporary` still renders the existing `select_slider` range and uses the label `区间冲击（interval）`.
- Add formatter-level assertions: midnight daily timestamps display as `YYYY-MM-DD` without `00:00:00`; timestamps with meaningful hours/minutes/seconds retain those components.

**Step 2: Run the focused UI tests**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py -k "rdl_intervention_controls or rdl_intervention_switches" -q
```

Expected: FAIL because the current implementation uses `select_slider` for `pulse`, the old temporary label, and the default timestamp string includes an unnecessary time suffix for daily data.

### Task 2: Implement mode-specific date controls

**Files:**
- Modify: `dashboard/models/SARIMAX/ui/model_options_rdl.py:193-267`
- Modify: `dashboard/models/SARIMAX/ui/state.py:32-41`

**Step 1: Add a dedicated pulse-date widget state suffix**

Add `intervention_pulse_date` to `_RDL_WIDGET_SUFFIXES` so the new widget is included in lifecycle cleanup and state handoff. Do not reuse `intervention_start` for a different Streamlit widget type.

**Step 2: Rename only the display label**

Change the mapping label from `临时区间冲击（temporary）` to `区间冲击（interval）`; keep the internal value `temporary` unchanged.

**Step 3: Add precision-aware timestamp formatting**

Add a small UI-only formatter that inspects the actual model timestamps and chooses the shortest format that preserves non-zero information: date only when all timestamps are at midnight, date plus hour when only hours vary, date plus minute when minutes are meaningful, and date plus seconds when seconds are meaningful. Pass this formatter as `format_func` to every intervention date widget. Keep the option objects and the resulting `RDLInterventionConfig` values as full `pd.Timestamp` objects; formatting must never call `.date()` or normalize the selected values.

**Step 4: Render controls by shock kind**

- `pulse`: render `st_obj.selectbox` with key `<prefix>_intervention_pulse_date`; return that date as `start_date` and `None` as `end_date`.
- `step`: render `st_obj.select_slider` in range mode with `(default_start, dates[-1])`; pin the upper endpoint back to `dates[-1]` before rendering on every rerun, use the lower endpoint as `start_date`, and return `None` as `end_date`. The red selection therefore always extends from the selected date to the end of the timeline.
- `temporary`: preserve the current range slider key, label, inclusive endpoint behavior, and `end_date` handling.

**Step 5: Preserve the existing backend contract**

Continue constructing `RDLInterventionConfig` with only the meaningful start/end dates. No changes are allowed in `rdl_config.py`, `rdl_modeling.py`, Ts event encoding, or RDL estimation.

### Task 3: Run regression verification

**Files:**
- No additional files.

**Step 1: Run the focused tests**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py -k "rdl_intervention" -q
```

Expected: all RDL intervention UI flow tests pass with no `AppTest` exception.

**Step 2: Run the required SARIMAX regression boundary suite**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
```

Expected: the documented SARIMAX regression suite passes.

**Step 3: Check the final diff**

```powershell
git diff --check
git status --short
```

Expected: only the intended UI, state-key, test, and plan files are changed; no cache or temporary artifacts are added.

**Acceptance criteria:**

1. `pulse` presents a point/date selector without a red interval bar.
2. `step` presents a red selection from the chosen start date through the final model date.
3. The `temporary` option is displayed as `区间冲击（interval）`, with the current interval-slider style and inclusive endpoints unchanged.
4. Daily timestamps display without minute/second suffixes, while actual selected values retain their complete timestamp precision for exact matching.
5. Internal values remain exactly `pulse`, `step`, and `temporary`; fitted model behavior is unchanged.
