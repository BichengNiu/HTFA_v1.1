# RDL/ARDL 手动阶数与 SARIMA 误差 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 HTFA 的 RDL 和 ARDL 都取消自动选阶，并允许用户分别手动指定其 ARDL/RDL 动态结构以及误差项 SARIMA 阶数；SARIMAX 自身的自动选阶保持不变。

**Architecture:** 先扩展 canonical `D:\Ts`：`ARDL` 增加可选的手动 SARIMA 误差结构，指定后复用现有 Ts `SARIMAX` 状态空间实现估计和预测；未指定误差结构时保留当前 OLS ARDL 行为。随后 HTFA 的 `ARDLConfig` 持有手动 `SARIMAXConfig` 误差配置，RDL 继续持有同类误差配置；HTFA 删除 RDL/ARDL 的自动配置和自动选阶路由，但不删除 Ts 库自身已有的 `AutoARDL` 公共 API。

**Tech Stack:** Python dataclasses, statsmodels ARDL/SARIMAX, Streamlit/AppTest, pytest, HTFA runtime Python, canonical `D:\Ts` package APIs.

---

### Task 1: 为 Ts ARDL+SARIMA 误差建立失败测试

**Files:**
- Modify: `D:\Ts\TsModels\tests\test_ardl.py`
- Modify: `D:\Ts\TsModels\_ardl.py` only if a test helper is required; production implementation belongs in Task 2

**Step 1: 写手动误差阶数测试**

- 构造带日期、目标滞后和输入滞后的模拟数据。
- 调用 `ARDL(..., error_order=(1, 0, 1), error_seasonal_order=(0, 0, 0, 0), ...)`。
- 断言拟合结果保留 ARDL 目标/输入滞后，并暴露 `error_order`、`error_seasonal_order`、`error_likelihood_burn` 或等价的有效样本信息。
- 断言参数中同时存在 ARDL 回归项和 SARIMA 误差参数，结果可生成摘要和残差诊断。

**Step 2: 写手动误差预测测试**

- 用完整的未来外生变量路径调用 `predict(start=n, end=n+2, future_exog=...)`。
- 断言均值、区间长度为 3，且全部为有限值。
- 断言日期模型的预测日期连续且从样本末期之后开始。

**Step 3: 保留无误差结构的 OLS 兼容测试**

- 现有未设置 `error_order` 的 ARDL 与 statsmodels OLS 对齐断言保持不变。
- 增加断言默认 `ARDL(...).fit()` 的 `error_order is None`，不会意外切换到 SARIMA 状态空间路径。

**Step 4: 运行 Ts 单文件测试，确认新测试失败**

Run:

```powershell
runtime\python.exe -m pytest -q D:\Ts\TsModels\tests\test_ardl.py
```

Expected: 新增的误差结构测试因当前 `ARDL` 不接受 `error_order` 而失败；原有 ARDL 测试保持通过。

---

### Task 2: 在 Ts 中实现手动 ARDL+SARIMA 误差

**Files:**
- Modify: `D:\Ts\TsModels\_ardl.py`
- Add: `D:\Ts\docs\ardl-sarima-error.md`
- Modify: `D:\Ts\TsModels\demo.ipynb` only if the existing executable example is updated without保存生成输出

**Step 1: 扩展 ARDL 构造参数并补齐公共 docstring**

- 增加 `error_order=None`、`error_seasonal_order=(0, 0, 0, 0)`、`error_enforce_stationarity=True`、`error_enforce_invertibility=True`。
- `error_order is None` 时保留旧 OLS 逻辑；若只指定非零 `error_seasonal_order` 则抛出明确错误。
- 使用现有 `_sarimax.py` 的阶数、布尔值和协方差/拟合参数校验，不复制校验实现。
- 公共构造函数 docstring 覆盖新增参数，满足 Ts 的 public-help 完整性测试。

**Step 2: 复用现有状态空间实现**

- 使用 statsmodels ARDL 已构造好的有效样本 `_y`、回归设计 `_x`、`exog_names` 和 deterministic process，形成带日期的 ARDL 回归设计。
- 指定误差阶数时调用现有 Ts `SARIMAX`，以 `trend="n"` 拟合 ARDL 设计系数和 SARIMA 误差；不把 ARDL 的目标滞后错误映射为 SARIMA AR 系数。
- 复用 Ts SARIMAX 的拟合、收敛要求、状态初始化、预测区间和残差语义。

**Step 3: 扩展 ARDLResult**

- 增加误差阶数和误差结果的稳定属性。
- 保留现有 ARDL `ar_lags`、`distributed_lags`、`ardl_order`、参数和摘要契约。
- SARIMA 误差路径的 `converged`、`optimizer`、有效样本、残差和诊断委托给复用的状态空间结果。
- 摘要同时显示 ARDL 目标/输入滞后和 Error SARIMA 阶数。

**Step 4: 实现递归未来设计和预测**

- 使用 statsmodels deterministic process 生成未来确定性项。
- 按实际/递归预测的目标值构造未来目标滞后，按历史+未来路径构造输入滞后，确保回归设计列与拟合列一一对应。
- 对日期边界、未来外生变量列名、长度、非有限值和动态预测保持现有 ARDL 约束。
- 不改变未指定误差结构时的原有预测路径。

**Step 5: 运行 Ts 测试和文档契约**

Run:

```powershell
runtime\python.exe -m pytest -q D:\Ts\TsModels\tests\test_ardl.py D:\Ts\tests\test_public_docstrings.py
```

Expected: 新增 ARDL+SARIMA 误差测试和原有 ARDL 测试通过；公共 docstring
测试不应新增由本次接口造成的失败。

---

### Task 3: 提交并同步 Ts 运行时

**Files:**
- Modify: `D:\Ts\TsModels\_ardl.py` and its Ts tests/docs from Tasks 1–2
- Sync: `D:\HTFA_v1.1\runtime\Lib\site-packages\Ts\TsModels\_ardl.py`

**Step 1: 检查 Ts 分支和远端关系**

Run:

```powershell
git -C D:\Ts branch --show-current
git -C D:\Ts status --short
git -C D:\Ts rev-list --left-right --count main...origin/main
```

Expected: 当前分支为 `main`；除本次修改外无用户工作；再继续提交。

**Step 2: 运行 Ts 相关质量门禁**

Run from `D:\Ts`:

```powershell
runtime\python.exe -m pytest -q tests TsModels/tests
git diff --check
```

Expected: 全部 Ts 基线及 ARDL 新测试通过，差异无空白错误。

**Step 3: 提交并推送 Ts**

- 使用 Conventional Commit，例如 `feat(models): support manual SARIMA errors in ARDL`。
- 提交前确认仍在 `main`，然后推送 `origin main`。
- 推送后确认 `main...origin/main` 为 `0 0`。

**Step 4: 同步运行时并验证哈希**

- 将 canonical `_ardl.py` 复制到 HTFA runtime 对应目录。
- 对 canonical 与 runtime 文件执行 SHA-256 校验，确认内容一致。

---

### Task 4: HTFA 配置与 UI 固定为手动 RDL/ARDL，并接入 ARDL 误差配置

**Files:**
- Modify: `dashboard/models/SARIMAX/core/ardl_config.py`
- Modify: `dashboard/models/SARIMAX/core/rdl_config.py`
- Modify: `dashboard/models/SARIMAX/core/ardl_modeling.py`
- Modify: `dashboard/models/SARIMAX/core/rdl_modeling.py`
- Modify: `dashboard/models/SARIMAX/core/modeling.py`
- Modify: `dashboard/models/SARIMAX/core/model_config.py`
- Modify: `dashboard/models/SARIMAX/core/__init__.py`
- Modify: `dashboard/models/SARIMAX/core/adapters.py`
- Modify: `dashboard/models/SARIMAX/core/result_views.py`
- Modify: `dashboard/models/SARIMAX/ui/pages/sections/training_section.py`
- Modify: `dashboard/models/SARIMAX/ui/model_options.py`
- Modify: `dashboard/models/SARIMAX/ui/model_options_rdl.py`
- Modify: `dashboard/models/SARIMAX/ui/model_options_ardl.py`
- Modify: `dashboard/models/SARIMAX/ui/model_options_sarimax.py`
- Modify: `dashboard/models/SARIMAX/ui/state.py`

**Step 1: 扩展 HTFA ARDLConfig**

- 增加 `error: SARIMAXConfig`，并把误差签名纳入 `ARDLConfig.signature()`。
- 保留直接构造 `ARDLConfig` 时 `error=None` 的兼容 OLS 路径，HTFA UI 始终传入手动 `SARIMAXConfig`。
- `validate_fit_inputs()` 同时检查 ARDL 确定性季节周期和误差 SARIMA 季节周期。

**Step 2: 固定 HTFA RDL/ARDL 为手动配置**

- 训练页只为 SARIMAX 渲染“手动配置/自动选阶”；RDL/ARDL 的 mode 固定为“手动配置”。
- RDL 固定使用 `rdl_error_*` 手动 SARIMA 控件和 `RDLConfig`，删除自动误差搜索分支。
- ARDL 增加 `ardl_error_*` 手动 SARIMA 控件，同时保留手动目标滞后和逐变量输入滞后；删除最大阶数、准则和搜索方式控件。
- ARDL 的 SARIMA 误差拟合参数统一从该误差配置传入 Ts；不把误差 AR 阶数混同为 ARDL 目标滞后。

**Step 3: 删除 HTFA RDL/ARDL 自动路由和候选视图**

- 删除 `AutoRDLConfig`、`AutoARDLConfig` 及 HTFA `fit_auto_rdl()`、`fit_auto_ardl()` 的配置/路由/导出。
- `is_automatic_config()` 和自动进度条只保留 SARIMAX。
- RDL/ARDL 结果视图只显示单一手动拟合结果，不渲染自动候选表。
- 保留 Ts 包 `AutoARDL`，因为它不属于 HTFA 页面入口。

**Step 4: 清理 widget 状态**

- RDL 删除 `auto_error_*` 和候选选择键；ARDL 删除 `auto_*` 键；`config_mode` 只注册给 SARIMAX。
- 保留 SARIMAX 自动选阶状态和结果选择键。

---

### Task 5: HTFA 回归测试、质量验证和交付

**Files:**
- Modify: `tests/models/test_sarimax_modeling.py`
- Modify: `tests/models/test_sarimax_ui_flow.py`
- Modify: `tests/models/test_model_workflow_contract.py` only when the adapter contract needs a focused assertion

**Step 1: 更新核心测试**

- RDL 测试断言手动误差阶数传入并保留传递函数。
- ARDL 测试断言手动目标/输入滞后和手动误差 SARIMA 阶数均进入 Ts 结果。
- 删除 HTFA RDL/ARDL 自动拟合测试，保留 SARIMAX 自动选阶测试。

**Step 2: 更新 AppTest 流程**

- RDL/ARDL 页面不再出现配置方式切换、自动范围 slider、自动进度条或候选结果表。
- 两个页面都能显示 `*_error_p/d/q/P/D/Q/s` 手动控件，并能完成拟合。
- 设置非默认误差阶数后，读取会话中的拟合结果，断言误差 `order`/`seasonal_order` 与输入一致。
- ARDL 结果同时保留 `ardl_order` 和误差 SARIMA 阶数；预测流程仍可提供未来外生变量。

**Step 3: 运行最终验证**

Run:

```powershell
runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_modeling.py tests\models\test_sarimax_ui_flow.py tests\models\test_model_workflow_contract.py -q
runtime\python.exe -B -m compileall -q htfa\models\univariate\sarimax
rg -n -S "AutoRDLConfig|AutoARDLConfig|fit_auto_rdl|fit_auto_ardl|rdl_auto_|ardl_auto_|rdl_config_mode|ardl_config_mode" dashboard tests components
git diff --check
```

Expected: HTFA 针对性测试全部通过；静态检查不再发现 RDL/ARDL 自动入口；SARIMAX 自动入口仍存在；编译和差异检查通过。

**Step 4: 提交与交付**

- 确认 HTFA 当前分支为 `main`，提交正式源文件和测试；不添加缓存、数据库、原始数据或临时文件。
- 若执行 push，先运行 `tooling\scripts\clean_temps.ps1`，复核 `git status --short`，再推送 `origin main`。
- 交付时提醒重启 `scripts\start.bat`，因为 Streamlit 会缓存已加载模块。
