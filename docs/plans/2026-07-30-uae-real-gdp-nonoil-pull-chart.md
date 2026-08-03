# UAE Real GDP and Non-oil Pull Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Replace the separate growth trend and oil/non-oil snapshot with one chart titled “实际GDP增速与非石油经济部门拉动率”.

**Architecture:** Keep all statistical calculations in `services.py` and all Plotly construction in `charts.py`. Calculate the non-oil pull from constant-price GDP levels, add it to the existing three YoY growth series, and let the renderer use a dedicated line-and-bar chart for that named group while leaving other panels unchanged.

**Tech Stack:** Python 3.11, pandas, Plotly, Streamlit, pytest.

---

### Task 1: Define the combined chart contract

**Files:**
- Modify: `tests/analysis/uae/test_renderer.py`
- Modify: `tests/analysis/uae/test_services.py`

**Step 1: Write the failing tests**

Assert that the growth frame contains the three YoY line columns plus
`【真实】非石油经济部门拉动`, and that the dedicated figure renders the pull
as a bar with the other series as lines.

**Step 2: Run tests to verify they fail**

Run:
`python -m pytest tests/analysis/uae/test_renderer.py tests/analysis/uae/test_services.py -q`

Expected: failure because the combined figure and pull column do not exist.

### Task 2: Implement the calculation and chart

**Files:**
- Modify: `dashboard/analysis/uae/services.py`
- Modify: `dashboard/analysis/uae/charts.py`

**Step 1: Calculate the non-oil pull**

Use:

```python
non_oil_pull = (
    nonoil - nonoil.shift(4)
).div(real_gdp.shift(4)) * 100
```

Store it beside the three existing YoY series under the confirmed chart title.

**Step 2: Build the combined figure**

Render the pull column with `go.Bar` and all other columns with `go.Scatter`.
Use a shared zero line and label the axis `同比增速（%）/ 拉动（百分点）`.

### Task 3: Render without duplication

**Files:**
- Modify: `dashboard/analysis/uae/renderer.py`

Use the combined figure only for the confirmed growth group. Do not render the
old oil/non-oil latest-contribution chart; retain the industry contribution
chart and all other panels.

### Task 4: Validate

Run:

```text
python -m pytest tests/analysis/uae/test_growth.py tests/analysis/uae/test_services.py tests/analysis/uae/test_renderer.py -q
python -m compileall -q app.py dashboard tests
git diff --check
```

Expected: all tests pass, compilation succeeds, and no whitespace errors are
reported.
