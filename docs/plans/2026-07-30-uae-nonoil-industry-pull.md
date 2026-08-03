# UAE Non-oil Industry Pull Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Remove the nominal-real bridge and replace the latest total-GDP industry contribution chart with a quarterly stacked-bar and line chart whose non-oil industry pulls reconcile exactly to quarterly non-oil real GDP YoY growth.

**Architecture:** Keep the workbook parser unchanged, map all 16 non-oil constant-price industry series now present in `季度_Wind`, and calculate the quarterly accounting decomposition inside the UAE growth service. Across the full data range, rank industries by the arithmetic mean of quarterly real-GDP shares, keep the top five fixed across all quarters, and aggregate the remaining industries as `其他行业`.

**Tech Stack:** Python 3.11, pandas, Plotly, Streamlit, pytest.

---

## Chart Contract

- Analytical question: Which non-oil industries pulled quarterly non-oil real GDP YoY growth up or down?
- Chart: signed relative stacked bars for industry pull contributions plus one dark line for non-oil real GDP YoY.
- Grain: 52 quarterly YoY observations, 2013Q1–2025Q4.
- Denominator: prior-year same-quarter non-oil real GDP.
- Unit: bars in percentage points; line in percent.
- Categories: the five industries with the highest full-range average quarterly share plus `其他行业`; no residual category.
- Reconciliation: every quarterly stacked-bar total must equal the non-oil GDP YoY line within floating-point tolerance.
- Palette: fixed category colors; negative values remain below zero through Plotly `relative` stacking.
- Surface: existing Streamlit growth tab, full container width.

### Task 1: Lock the accounting contract with failing tests

**Files:**
- Modify: `tests/analysis/uae/test_services.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Step 1: Add service tests**

Assert that:

```python
frame = panel.series_groups["非油实际GDP同比及行业拉动"]
assert "采矿和采石" not in frame
assert "其他非油行业、税收与统计差异" not in frame
assert len(frame.drop(columns="【真实】非油GDP同比").columns) == 16
pd.testing.assert_series_equal(
    frame.drop(columns="【真实】非油GDP同比").sum(axis=1),
    frame["【真实】非油GDP同比"],
    check_names=False,
)
```

Also assert that `名义—实际桥接` is absent and the growth panel no longer exposes the old latest industry decomposition table.

**Step 2: Add chart tests**

Construct a two-quarter sample and assert that the new figure contains stacked bar traces, one line trace, `barmode="relative"`, quarterly x-values, and the declared y-axis unit.

**Step 3: Run the tests and verify failure**

Run:

```text
python -m pytest tests/analysis/uae/test_services.py tests/analysis/uae/test_renderer.py -q
```

Expected: failure because the fixed Top-5-by-average-share frame and dedicated figure do not exist.

### Task 2: Calculate quarterly non-oil industry pulls

**Files:**
- Modify: `dashboard/analysis/uae/services.py`

**Step 1: Map all 16 non-oil industries**

Update `INDUSTRY_NAMES` and the stable semantic IDs to match the 16 non-oil
constant-price level columns in `季度_Wind`. Do not include mining.

**Step 2: Validate quarterly level additivity**

At quarterly level verify:

```python
residual = nonoil_real_gdp - all_16_nonoil_industries.sum(axis=1)
assert residual.abs().max() <= 1e-5
```

Do not create or distribute a residual component. The observed maximum
difference is `0.000004` million AED, caused by six-decimal workbook rounding.

**Step 3: Calculate quarterly pull contributions**

Use the existing `calculate_growth_contributions` function with:

```python
total=quarterly_nonoil_real_gdp
components=quarterly_nonoil_components
periods=4
```

For each industry:

```python
pull_i_y = (
    industry_i_y - industry_i_y_minus_1
) / nonoil_gdp_y_minus_1 * 100
```

The component sum must equal:

```python
(nonoil_gdp_y / nonoil_gdp_y_minus_1 - 1) * 100
```

**Step 5: Remove nominal analysis**

Delete the nominal GDP requirement, nominal-real bridge calculation and frame, nominal provenance entry, bridge methodology note, and `名义—实际桥接` series group.

### Task 3: Render the quarterly stacked-bar and line chart

**Files:**
- Modify: `dashboard/analysis/uae/charts.py`
- Modify: `dashboard/analysis/uae/renderer.py`

**Step 1: Add a dedicated figure builder**

Add `build_nonoil_industry_pull_figure`. Treat `【真实】非油GDP同比` as the only line and every other column as a stacked bar component.

**Step 2: Apply stable visual semantics**

- Use `barmode="relative"`.
- Use a dark line with visible markers.
- Use `季度` on the x-axis and lock chronological category order.
- Use `同比增速（%）/ 行业拉动（百分点）` on the y-axis.
- Keep the legend above the chart and allow wrapping.

**Step 3: Route the frame in the renderer**

Select the dedicated figure by the stable group title
`非油实际GDP同比及行业拉动`; leave all other panel rendering unchanged.

### Task 4: Validate the real workbook and regressions

**Files:**
- Verify: `data/阿联酋.xlsx`
- Verify: `dashboard/analysis/uae/services.py`
- Verify: `dashboard/analysis/uae/charts.py`

**Step 1: Verify real-data reconciliation**

Expected real-workbook results:

- quarterly growth periods: 2013Q1–2025Q4;
- 2025Q4 non-oil real GDP YoY: approximately `8.088030%`;
- 2025Q4 stacked component sum: approximately `8.088030` percentage points;
- maximum quarterly reconciliation error: below `1e-8` percentage points.

**Step 2: Run targeted tests**

```text
python -m pytest tests/analysis/uae/test_growth.py tests/analysis/uae/test_services.py tests/analysis/uae/test_renderer.py -q
```

Expected: all pass.

**Step 3: Run broader checks**

```text
python -m pytest tests/analysis/uae --ignore=tests/analysis/uae/test_navigation.py -q
python -m compileall -q app.py dashboard tests
git diff --check
```

Expected: all available tests pass, compilation succeeds, and no whitespace errors are reported.

**Step 4: Review the dirty worktree before any commit**

Do not commit until the existing unrelated and overlapping user changes have been reviewed and the user explicitly authorizes a commit.
