# UAE Enterprise Activity Payment Charts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 HTFA 的“企业活动”部分，在现有 DED 与 PMI 图表下方增加 FTS 客户转账和支票清算两张双轴月度图。

**Architecture:** 复用现有 `月度_CBUAE` 前六行元数据协议，新增一个支付数据模块读取四个已有指标；使用运行时已有的 `Ts.TsPlots.plot_series` 绘制“笔数/金额”双轴折线图。渲染层只负责缓存、布局、错误隔离和下载，数据解析与图表构建留在模块内。

**Tech Stack:** Python, pandas, openpyxl, matplotlib, Streamlit, `Ts.TsPlots.plot_series`, pytest。

---

### Task 1: Add payment data loader and figure builders

**Files:**
- Create: `dashboard/analysis/uae/government_finance/payments.py`
- Test: `tests/analysis/uae/test_payments.py`

**Step 1: Write the failing tests**

Add a mixed-unit `月度_CBUAE` fixture containing these existing indicators:

- `阿联酋:FTS客户转账笔数(累计)Customer Transfers Number` — `笔`
- `阿联酋:FTS客户转账金额(累计)Customer Transfers Amount` — `百万迪拉姆`
- `阿联酋:支票清算笔数(累计)Cheques Cleared Number` — `张`
- `阿联酋:支票清算金额(累计)Cheques Cleared Amount` — `百万迪拉姆`

Test that `load_payment_data()` preserves the four display columns, metadata units, dates, and rejects missing/invalid fields. Test both builders for a 37-month window, two plotted series, separate count/amount y-axes, units, source note, and the war reference line.

**Step 2: Run the focused tests to verify they fail**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\analysis\uae\test_payments.py -q
```

Expected: collection/import failure because `payments.py` and its public loader/builders do not exist yet.

**Step 3: Implement the minimal module**

Implement:

- constants for the four source indicator names and four display labels;
- immutable `PaymentData(values, metadata, source_name)`;
- strict mixed-unit parser for `月度_CBUAE`, following `ded.py`'s metadata validation and numeric-value handling;
- `load_payment_data(file_input, file_name=None)`;
- a shared private two-series figure helper using `within_month_window`, `plot_series(facet=False, axis_groups=...)`, `year_ruler=True`, `grid=True`, `vlines=WAR_START_DATE`, `show_legend=True`, source note, `figsize=(9.4, 6.2)`, and per-series units;
- public `build_customer_transfers_figure()` and `build_cheques_figure()` wrappers, with titles explicitly stating “年内累计”.

Keep the raw cumulative/YTD values as supplied by the workbook; do not silently convert them to monthly increments. The chart title/note must make the cumulative nature visible.

**Step 4: Run the focused tests to verify they pass**

Run the same pytest command. Expected: all payment loader and figure tests pass.

### Task 2: Place the two charts under the existing business-activity charts

**Files:**
- Modify: `dashboard/analysis/uae/government_finance/renderer.py`
- Modify: `dashboard/analysis/uae/government_finance/__init__.py` only if the package currently requires explicit exports
- Test: `tests/analysis/uae/test_government_finance.py`

**Step 1: Extend renderer dependencies and cache**

Import `PaymentData`, `build_customer_transfers_figure`, `build_cheques_figure`, `load_payment_data`, and display/unit constants. Add `_load_payment_cached()` with the same `st.cache_data` pattern as the existing loaders.

**Step 2: Add isolated chart renderers**

Add `_render_customer_transfers_chart()` and `_render_cheques_chart()` beside `_render_ded_chart()` and `_render_pmi_chart()`. Each renderer must:

- anchor the display window to `latest_date`;
- call its payment figure builder;
- call `render_pyplot_figure(..., bbox_inches=None, place_legend_bottom=False)`;
- expose a unique `render_chart_download()` key;
- keep source/unit metadata in the chart and download frame.

**Step 3: Add the second business-activity row**

In `_render_business_activity_charts()`, keep the existing DED/PMI two-column row unchanged. Add a second `st_obj.columns(2, gap="small")` row immediately below it, with customer transfers on the left and cheque clearing on the right. Load payment data once, but wrap the two chart render calls independently so one missing/invalid chart does not suppress the other. Add the cumulative-data explanation to `BUSINESS_ACTIVITY_EXPLANATION`.

**Step 4: Update renderer tests**

Extend mocks for the payment loader and both renderers. Update the expected `columns` call count from 4 to 5 and assert both new renderers are called once. Add a failure-isolation assertion for a payment chart warning.

### Task 3: Verify the complete requested boundary

**Files:**
- No additional source files.

**Step 1: Run focused regression tests**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\analysis\uae\test_payments.py tests\analysis\uae\test_government_finance.py tests\analysis\uae\test_credit.py tests\analysis\uae\test_ded.py tests\analysis\uae\test_pmi.py -q
```

Expected: all focused UAE government-finance tests pass.

**Step 2: Run the broader UAE analysis tests if the focused suite passes**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\analysis\uae -q
```

Expected: no regression in other UAE analysis panels.

**Step 3: Inspect the final diff**

```powershell
git diff -- dashboard/analysis/uae/government_finance/renderer.py dashboard/analysis/uae/government_finance/payments.py tests/analysis/uae/test_government_finance.py tests/analysis/uae/test_payments.py docs/plans/2026-08-22-uae-payment-charts.md
```

Confirm that only the requested chart/module/test/plan files are changed in this task; preserve all pre-existing dirty-worktree files. Restart `scripts\start.bat` before viewing the Streamlit result because the process caches imported modules.
