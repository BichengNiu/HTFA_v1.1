# 单变量预测评估双 Tab Implementation Plan

> **Archive:** 历史计划，仅保留迁移前路径记录；其中路径不可作为运行入口。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将单变量模型预测评估改为“训练期评估”和“样本外评估”两个 Tab，并在每个 Tab 内同时支持完整窗口指标与可选 H 期滚动结果。

**Architecture:** 纯评估层负责构造四种评估报告和按预测步长聚合结果；模型编排层负责准备处理后的训练/验证序列、固定起点预测和 Ts 滚动评估；页面层只负责 Tab、H 控件、按钮、表格、图形和下载。训练期 H 期结果是训练集内部伪样本外验证，样本外 H 期结果是训练结束日后的扩展窗口滚动回测。

**Tech Stack:** Python 3.13、pandas、NumPy、Streamlit、Ts.TsMetrics (`RollingOrigin` / `evaluate_forecasts`)、openpyxl、pytest、Streamlit AppTest。

---

## 约定

- H 控件范围为 1–12，step 固定为 1。
- 滚动窗口为 expanding，滚动步长固定为 1。
- 训练期 H 期滚动的初始训练样本数为 `max(MIN_OBSERVATIONS, 2 * H)`；不足以形成一个完整 H 期验证窗口时明确提示，不伪造指标。
- 样本外完整窗口只使用训练结束日之后、数据中已经存在真实值的日期；未来延伸日期不参与评分。
- “完整窗口”与“H 期滚动”即使日期重叠也不要求数值相等：前者固定一次拟合结果，后者每个滚动起点重新拟合。
- 主误差指标仍为 MAE、RMSE、MPE、MAPE、sMAPE；方向指标仍为方向命中率、相对基准胜率和趋势相关系数。

### Task 1: 扩展纯评估报告与按步长聚合

**Files:**
- Modify: `dashboard/models/common/forecast_evaluation.py`
- Test: `tests/models/test_forecast_evaluation.py`

**Step 1: Write the failing tests**

在现有纯逻辑测试中增加以下断言：

```python
def test_rolling_report_contains_overall_and_by_horizon_tables():
    report = evaluate_rolling_forecast(..., horizon=3)

    assert report.horizon_error_table is not None
    assert report.horizon_direction_table is not None
    assert report.horizon_error_table["步长"].tolist() == [1, 2, 3]
    assert report.horizon_direction_table["步长"].tolist() == [1, 2, 3]
```

增加训练集内部伪样本外测试，验证 `initial_window=max(10, 2H)` 时完整窗口数量、验证窗口数量和每个步长的数量都正确；增加无完整 H 期窗口时返回明确的空报告/提示，而不是填充零值。

**Step 2: Run tests to verify they fail**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_forecast_evaluation.py -q
```

Expected: FAIL because `ForecastAccuracyReport` 尚无按步长表，且没有训练期滚动评估入口。

**Step 3: Implement the minimal pure logic**

- 为 `ForecastAccuracyReport` 增加可选字段 `horizon_error_table` 和 `horizon_direction_table`，默认 `None`，保持完整窗口报告仍可复用。
- 增加 `evaluate_in_sample_fit(actual, fitted, dates, ...)`，只评价有限的拟合值，输出单行“完整训练期拟合”报告。
- 增加 `evaluate_fixed_holdout(actual, predicted, dates, ...)`，输出单行“完整样本外验证”报告，并与朴素基准共享误差/方向计算。
- 将 `evaluate_rolling_forecast` 的逐点表保留“步长”列，按“整体”和“步长”分别调用现有 `_summary_row` / `_direction_row`，生成 overall 与 by-horizon 两组表。
- 增加 `evaluate_training_rolling(...)`，复用相同的 Ts `RollingOrigin` 结果消费逻辑，只把数据限制在训练样本，并在 `initial_window=max(10, 2*horizon)` 前置校验。
- 对基准行继续计算 MAE、RMSE、MPE、MAPE、sMAPE、方向命中率和趋势相关系数；相对基准胜率只在模型行生成，基准行用 `NaN` 表示不适用。

**Step 4: Run tests to verify they pass**

Run the focused test file again. Expected: all existing and new pure evaluation tests pass.

**Step 5: Commit**

```powershell
git add dashboard/models/common/forecast_evaluation.py tests/models/test_forecast_evaluation.py
git commit -m "feat(metrics): split forecast evaluation windows"
```

### Task 2: 增加模型层的训练/验证数据编排

**Files:**
- Modify: `dashboard/models/SARIMAX/core/modeling.py`
- Modify: `dashboard/models/common/workflow.py`
- Modify: `dashboard/models/SARIMAX/core/adapters.py`
- Test: `tests/models/test_model_workflow_contract.py`
- Test: `tests/models/test_forecast_evaluation.py`

**Step 1: Write the failing tests**

增加 adapter contract 测试，要求三类模型均能提供：

```python
context = workflow.forecast_context(result)
fitted = workflow.fitted_values(result)
assert len(fitted) == context.model_nobs
```

增加编排测试，验证：固定起点样本外评估只返回训练结束日之后的已有真实值；训练期滚动和样本外滚动的 `RollingOrigin` 初始窗口、目标日期和 H 一致。

**Step 2: Run tests to verify they fail**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_model_workflow_contract.py tests\models\test_forecast_evaluation.py -q
```

Expected: FAIL because `ModelWorkflow.fitted_values` 和固定起点/训练期滚动编排尚不存在。

**Step 3: Implement the model boundary**

- 在 `ModelAdapter` 协议和 `ModelWorkflow` 增加 `fitted_values(result)`，由 `_TsResultAdapter` 对 `_best_result(result).fitted_values` 做 NumPy 一维化和长度校验。
- 将 `_backtest_inputs` 提取为共享的完整处理后序列构造函数，返回 `series`、`exog`、`dates`、训练结束位置和训练期切片，确保训练期、固定验证和滚动回测使用同一处理后数据。
- 在 `modeling.py` 增加 `run_fixed_holdout_evaluation(...)`：复用当前已拟合结果，不重新拟合，只预测训练结束日后的已有观测；外生变量使用观测到的未来路径。
- 将现有 `run_historical_rolling_evaluation(...)` 参数化为评估区间，保留样本外滚动路径；新增训练期滚动调用，使用同一模型结构和 Ts `evaluate_forecasts`，只改变数据边界和初始窗口。
- 自动 SARIMAX 继续固定当前选中的模型阶数，不在每个滚动窗口重新选阶。

**Step 4: Run tests to verify they pass**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_model_workflow_contract.py tests\models\test_forecast_evaluation.py -q
```

Expected: all focused model orchestration tests pass for SARIMAX、RDL、ARDL。

**Step 5: Commit**

```powershell
git add dashboard/models/SARIMAX/core/modeling.py dashboard/models/common/workflow.py dashboard/models/SARIMAX/core/adapters.py tests/models/test_model_workflow_contract.py tests/models/test_forecast_evaluation.py
git commit -m "feat(models): add fixed holdout evaluation paths"
```

### Task 3: 重组页面为训练期/样本外两个 Tab

**Files:**
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/forecast_section.py`
- Modify: `dashboard/models/SARIMAX/ui/state.py`
- Modify: `dashboard/models/SARIMAX/ui/standalone_model.py`
- Test: `tests/models/test_sarimax_ui_flow.py`

**Step 1: Write the failing UI tests**

在现有 AppTest 中增加断言：

- Tab 标签恰为“训练期评估”“样本外评估”。
- 训练期显示完整拟合结果和训练期 H 期滚动控件。
- 样本外显示完整验证结果和样本外 H 期滚动控件。
- 训练结束日后没有真实观测时，样本外 Tab 显示明确的“暂无可评分样本”。
- 运行两个 H 期按钮后，状态中分别保存独立结果，切换 Tab 不会显示另一个 Tab 的报告。

**Step 2: Run tests to verify they fail**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py -q
```

Expected: FAIL because当前页面仍使用“当前预测窗口/历史滚动回测”两个 Tab。

**Step 3: Implement the UI flow**

- 将 `_render_forecast_evaluation` 改为创建两个 Tab，并分别调用：
  - `_render_training_evaluation(...)`
  - `_render_oos_evaluation(...)`
- 训练期 Tab：直接展示 `workflow.fitted_values(result)` 的完整训练期拟合报告；提供 H number input 与“运行训练期 H 期滚动验证”按钮。
- 样本外 Tab：展示固定起点完整验证窗口；提供 H number input 与“运行样本外 H 期滚动回测”按钮。
- 每个滚动报告同时展示 overall 表与按 `步长` 分组的误差/方向表；下载使用独立 key 和独立文件名，避免两个 Tab 互相覆盖。
- 报告标题、说明文字和状态提示明确写出：是否重新拟合、训练窗口、验证窗口、H、step=1、有效样本数和覆盖率。
- 更新 `state.py` 的 widget suffix、downstream lifecycle 和 `standalone_model.py` 的恢复/导出字段，分别保存训练期滚动报告和样本外固定/滚动报告。
- 训练期完整拟合不再依赖用户把预测滑轨停在训练结束日；样本外完整验证不把未来无真实值的日期纳入评分。

**Step 4: Run tests to verify they pass**

Run the affected UI tests and inspect AppTest dataframes, warnings, exceptions, buttons, and tab labels. Expected: no exceptions, both tabs present, OOS sample counts only reflect observed post-training dates.

**Step 5: Commit**

```powershell
git add dashboard/models/SARIMAX/ui/pages/sections/forecast_section.py dashboard/models/SARIMAX/ui/state.py dashboard/models/SARIMAX/ui/standalone_model.py tests/models/test_sarimax_ui_flow.py
git commit -m "feat(ui): split training and out-of-sample evaluation"
```

### Task 4: 完善滚动结果下载和图表一致性

**Files:**
- Modify: `dashboard/models/common/forecast_evaluation.py`
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/forecast_section.py`
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/forecast_chart.py`
- Test: `tests/models/test_forecast_evaluation.py`
- Test: `tests/models/test_sarimax_modeling.py`

**Step 1: Write the failing tests**

扩展 Excel 导出测试，要求滚动报告包含：

- `误差指标`
- `方向性指标`
- `误差指标_按步长`
- `方向性指标_按步长`
- `评估明细`

增加测试验证训练期和样本外滚动误差图都使用 Ts `plot_series`，且图形数据的日期、误差值与逐点明细完全一致。

**Step 2: Run tests to verify they fail**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_forecast_evaluation.py tests\models\test_sarimax_modeling.py -q
```

Expected: FAIL because当前工作簿没有按步长 sheet，页面下载仍只消费单一报告。

**Step 3: Implement export and rendering**

- 扩展 `build_accuracy_workbook`：有按步长表时按固定顺序写入 overall、by-horizon、detail sheet；没有按步长表时保持完整窗口导出结构。
- 复用已有 `render_forecast_error_chart`，统一消费每个报告的 `point_table`，不再使用 Streamlit 原生 `line_chart`。
- 为每个 Tab 的完整窗口和 H 期滚动结果使用一致的下载按钮样式、XLSX MIME 和文件名。

**Step 4: Run tests to verify they pass**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_forecast_evaluation.py tests\models\test_sarimax_modeling.py -q
```

Expected: all metric, workbook, chart and date/value consistency tests pass.

**Step 5: Commit**

```powershell
git add dashboard/models/common/forecast_evaluation.py dashboard/models/SARIMAX/ui/pages/sections/forecast_section.py dashboard/models/SARIMAX/ui/pages/sections/forecast_chart.py tests/models/test_forecast_evaluation.py tests/models/test_sarimax_modeling.py
git commit -m "feat(metrics): export rolling horizon breakdowns"
```

### Task 5: 更新领域文档并执行完整相关回归

**Files:**
- Modify: `CONTEXT.md`
- Modify: `docs/adr/0005-univariate-forecast-evaluation.md`
- Test: `tests/models/test_sarimax_boundaries.py`
- Test: `tests/models/test_sarimax_ui_flow.py`

**Step 1: Update documentation**

- 将 glossary 中的“当前预测窗口/历史滚动回测”更新为“训练期评估/样本外评估/完整窗口/H 期滚动”。
- 在 ADR 中记录四种报告的训练边界、是否重新拟合、H 和 step=1，明确训练期滚动是伪样本外验证。

**Step 2: Run focused regression suites**

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py tests\models\test_forecast_evaluation.py tests\models\test_model_workflow_contract.py tests\models\test_sarimax_modeling.py -q
```

Expected: all affected tests pass; allowed warnings must be reported separately from failures.

**Step 3: Verify dirty-worktree boundaries**

```powershell
git status --short
git diff -- dashboard/models/SARIMAX/ui/model_options_rdl.py dashboard/models/SARIMAX/ui/state.py tests/models/test_sarimax_ui_flow.py docs/plans/2026-09-03-rdl-intervention-time-controls.md
```

Expected: pre-existing RDL time-control changes remain intact and are not absorbed into feature commits.

**Step 4: Commit documentation**

```powershell
git add CONTEXT.md docs/adr/0005-univariate-forecast-evaluation.md
git commit -m "docs: clarify forecast evaluation protocols"
```

**Step 5: Runtime handoff**

Do not push unless explicitly requested. Remind the user to stop and restart `scripts\start.bat`, because Streamlit caches imported modules and a page refresh is insufficient.
