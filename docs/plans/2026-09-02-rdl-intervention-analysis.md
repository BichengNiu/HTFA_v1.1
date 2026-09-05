# RDL Intervention Analysis Implementation Plan

> **Archive:** 历史计划，仅保留迁移前路径记录；其中路径不可作为运行入口。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 HTFA 的 RDL 页面增加历史样本干预分析。用户勾选“干预分析”后，可在模型观测日期内选择 pulse、step 或 temporary 冲击，系统生成二元干预变量 I，并让 I 与普通外生变量 X 一样进入 RDL；拟合后展示 I 的路径、RDL 动态响应/稳态增益，以及目标变量在有无干预路径下的对比。

**Architecture:** 把 I 定义为由日期和类型确定的特殊外生变量，而不是修改 X，也不是直接向 Y 施加人为幅度。Ts 负责通用冲击路径生成和既有 RDL 传递函数；HTFA 负责 RDL 页面配置、状态签名、把 I 作为 RDL 输入拼入外生矩阵，以及基于 Ts 公开结果生成展示数据。第一版只支持历史训练样本、一个 I、三种 0/1 路径；普通 X 可以为空，但 X 与 I 不能同时为空。

**Tech Stack:** Python, pandas, Streamlit, statsmodels/SARIMAX, Ts `EventSpec`/`build_event_matrix`/`RationalLagResult`, pytest, Streamlit `AppTest`。

---

## 已确认的产品语义

- 模型结构同时包含 X 和 I：

  \[
  Y_t=\sum_i H_i(B)X_{i,t}+H_I(B)I_t+\varepsilon_t
  \]

- I 的数值编码固定为：无冲击期为 0，冲击期为 1；不提供“冲击幅度”输入，影响大小由 I 的 RDL 参数估计。
- `pulse`：选定观测期为 1，其余为 0。
- `step`：从选定观测期开始至训练样本末尾为 1。
- `temporary`：选定起止观测期组成包含端点的闭区间为 1。
- 日期只能从预处理后的实际模型观测日期中选择，不能选择训练样本之外或日期序列中不存在的任意日历日期。
- I 在 UI 中显示为独立的“干预变量 I”行，拥有与 X 相同的 numerator、denominator、delay/lag 结构；默认结构为即时直接效应（numerator=0、denominator=0、delay=0），用户可编辑。
- 勾选后允许只用 I 拟合；未勾选时保留现有 RDL 行为。X 和 I 都没有时拒绝拟合。
- 若 I 路径在样本内恒为 0、恒为 1，或与截距/趋势完全共线，明确提示并禁用/拒绝拟合；不自动移动日期、不缩短区间、不静默删除 I。
- 目标变量取对数时，在模型对数尺度估计；展示回到原始 Y 尺度，并用相对变化解释干预：`100 * (exp(delta_log_y) - 1)`。
- 现有“RDL 输入冲击响应”继续表示传递函数的动态权重；新增的“RDL 干预分析”单独表示按日期生成 I 后的样本路径和干预对比，二者不能混用。

## 实施顺序

### Task 1: 在 Ts 中补齐 temporary 冲击路径并建立回归测试

**Files:**

- Modify `D:\Ts\TsModels\_intervention.py`
- Modify `D:\Ts\TsModels\__init__.py`
- Modify/add `D:\Ts\TsModels\tests\test_intervention.py`
- Modify any related Ts public-docstring test fixture only if the public API requires it

**Steps:**

1. 先为 `EventSpec`/`build_event_matrix` 增加失败测试：`temporary` 必须有一个起点和一个终点，终点不能早于起点，必须按模型观测日期映射，并且起止端点都为 1；无关的 `window`/`reference` 参数应按现有契约拒绝或保持明确语义。
2. 扩展已有 `EventKind` 和矩阵生成逻辑，复用现有 exact/period/next/previous 日期解析；不要在 HTFA 重写一份日期匹配算法。
3. 保持 `pulse`、`step` 及既有构造函数的调用兼容性；新增字段不要破坏现有位置参数语义，优先追加字段并在内部使用关键字传递。
4. 从 `Ts.TsModels` 导出 `build_event_matrix`，补齐公共函数 docstring 的所有签名参数、返回值、异常和示例。
5. 验证 temporary 的单点区间、样本首尾区间、非连续模型日期、非法日期和逆序区间；同时回归 pulse/step。

**Verification:**

```powershell
Set-Location D:\Ts
..\HTFA_v1.1\runtime\python.exe -m pytest TsModels\tests\test_intervention.py TsModels\tests\test_distributed_lag.py -q
..\HTFA_v1.1\runtime\python.exe -m pytest tests\test_public_docstrings.py -q
```

Expected outcome: temporary 路径按闭区间生成，pulse/step 不回归，`from Ts.TsModels import build_event_matrix` 可用，新增公开 API 通过 docstring 检查。

### Task 2: 在 Ts 中确认 RDL 公共结果可支持干预对比

**Files:**

- Modify `D:\Ts\TsModels\tests\test_distributed_lag.py` only if a missing public-contract regression is identified
- Modify `D:\Ts\TsModels\_distributed_lag.py` only if the existing public `RationalLagResult.filter()` or `gain()` contract cannot represent the generated I path

**Steps:**

1. 用一个脉冲 I 和 numerator=0、denominator=0 的 RDL 拟合样本，验证 `result.distributed_lags["intervention"].filter(I)` 返回与样本对齐的动态响应。
2. 验证 `result.steady_state_gains`/RDL result 的 gain 能读取 I 的传递函数稳态增益。
3. 若现有公开 API 已满足，保持 Ts 最小改动，不新增重复的 effect API；HTFA 只组合 `filter()`、`gain()`、`result.fitted_values` 和 `result.log`。若不满足，先在 Ts 增加最小公共方法并为其补测试，再继续后续任务。

**Verification:** 同 Task 1 的 RDL focused tests，并检查 I-only 与 X+I 两种模型的输入顺序和结果字段。

### Task 3: 测试、推送并同步 Ts runtime

**Files:**

- Ts repository files changed in Tasks 1–2
- `D:\HTFA_v1.1\runtime\Lib\site-packages\Ts\TsModels\` corresponding runtime copies

**Steps:**

1. 在 `D:\Ts` 确认当前分支为 `main`，检查工作树，只提交本次 Ts 功能的正式源码和测试。
2. 运行 Ts focused tests；再运行仓库规定的 broader suite：

   ```powershell
   Set-Location D:\Ts
   ..\HTFA_v1.1\runtime\python.exe -c "import pytest, sys; sys.exit(pytest.main(['-q', 'tests', 'TsPlots/tests']))"
   ```

3. 若仍出现既有的 `TimeSeriesOperator-transformed_name` public docstring 失败，记录为预-existing failure，不把它归因于本功能；新增/修改测试不得失败。
4. 使用 Conventional Commit 提交 Ts 并推送 `main`；提交前核对 `git branch --show-current` 和本地/远端 `main` 关系。
5. 将实际改动的 Ts 模块同步到 `D:\HTFA_v1.1\runtime\Lib\site-packages\Ts\TsModels\`，然后用 runtime Python 导入并检查 `EventSpec`、`build_event_matrix` 和相关签名。

**Verification:** Ts `main` 提交成功、runtime copy 与源文件一致、runtime import 使用的是同步后的新 API。

### Task 4: 扩展 HTFA 建模输入和状态契约

**Files:**

- Modify `D:\HTFA_v1.1\dashboard\models\common\contracts.py`
- Modify `D:\HTFA_v1.1\dashboard\models\common\ui\model_inputs.py`
- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\ui\state.py`
- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\ui\pages\sections\training_section.py`
- Update boundary/model-input tests under `D:\HTFA_v1.1\tests\models\`

**Steps:**

1. 在 `ModelingInput` 增加默认关闭的 `intervention_analysis: bool`，只由 RDL 页面启用；保留 SARIMAX/ARDL 不显示该控件的行为。
2. 给 `ModelInputModule` 增加 `show_intervention=False`；RDL scope 传 `True`，其它模型传 `False`。
3. 将“干预分析” checkbox 放在“目标变量取对数”旁边；勾选/取消、目标变量变化、外生变量变化、训练样本变化都必须清除旧拟合结果和干预配置，防止 stale result。
4. 在 RDL scope 的 `WIDGET_KEYS`/suffix 中加入干预开关、类型、起点和终点等 key；把完整干预选择纳入 artifact signature。

**Verification:** 静态边界测试确认公共输入契约、widget key 汇总和 scope 隔离；AppTest 确认 checkbox 只出现在 RDL。

### Task 5: 扩展 RDL 配置与 UI

**Files:**

- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\core\rdl_config.py`
- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\ui\model_options.py`
- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\ui\model_options_rdl.py`
- Update `D:\HTFA_v1.1\tests\models\test_sarimax_modeling.py`
- Update `D:\HTFA_v1.1\tests\models\test_sarimax_ui_flow.py`

**Steps:**

1. 增加不可变的 `RDLInterventionConfig`，至少保存内部变量名 `intervention`、`kind`、`start_date`、`end_date`；`pulse`/`step` 只允许起点，`temporary` 要求起止点。
2. 将干预配置挂入 `RDLConfig`，并让 config signature 包含类型、日期以及 I 的全部 RDL 阶数/延迟；普通 X 的现有 config 结构保持不变。
3. 去除“必须有普通 exog 才能打开 RDL”的限制：启用干预且没有 X 时显示 I 行并允许拟合；未启用干预且没有 X 时仍按原规则拒绝。
4. 在 RDL 输入表中保留普通 X 行，并增加可见的 `I（干预变量）` 行。I 使用相同的 numerator、denominator、delay/lag 控件，不把它伪装成某个 X。
5. 增加冲击类型选择，中文选项严格映射为 `pulse`、`step`、`temporary`。pulse/step 使用一个基于实际模型观测日期的 `select_slider`；temporary 使用起止日期范围 slider，并保留闭区间语义。
6. 选择模型日期时只使用预处理后的训练 index；日期控件显示友好格式，但提交给 config 的值必须是可精确恢复的 `Timestamp`。
7. UI 层在路径恒为 0/1 或和截距/趋势共线时给出明确 warning/error，并使 fit 不可用；不得自动修正用户选择。

**Verification:** AppTest 覆盖：未勾选、勾选+X、仅 I、三种类型切换、temporary 端点、无效常数路径、修改日期后结果清空。现有普通 X RDL 流程继续通过。

### Task 6: 让 HTFA 训练流程把 I 作为 RDL 输入拟合

**Files:**

- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\core\rdl_modeling.py`
- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\core\modeling.py` only where the RDL input type/empty-X path requires it
- Add focused modeling tests under `D:\HTFA_v1.1\tests\models\`

**Steps:**

1. 从 `RDLInterventionConfig` 构造 Ts `EventSpec`，调用 runtime Ts 的公开 `build_event_matrix` 生成 `intervention`，按模型 index 与普通 X 对齐后追加到 exog；不使用 `events=` 作为直接回归列，因为 I 必须进入 RDL 传递函数。
2. 将 I 的 RDL spec 加入 `_rdl_specs(config)`，保持 ordinary X 顺序、I 的内部名稳定，并阻止用户普通 X 使用保留名 `intervention`。
3. 支持 `exog=None`/空 ordinary X 的 I-only 拟合；最终传入 Ts 的 exog 至少包含 I。
4. 在拟合前验证 I 的完整样本路径、索引、有限值、变异性和基本秩条件；把可解释的错误传回 UI。
5. 保留现有手动 RDL 阶数和误差结构行为，不引入自动选阶，也不改变非干预 RDL。

**Verification:** 直接测试 `X+I` 和 `I-only` 能拟合并在 `result.distributed_lags` 中包含 I；pulse/step/temporary 路径与 Ts 结果一致；非法路径在拟合前失败。

### Task 7: 增加干预分析结果展示

**Files:**

- Modify `D:\HTFA_v1.1\dashboard\models\SARIMAX\ui\pages\sections\analysis_section.py`
- Add/modify a focused HTFA result adapter module only if the existing analysis utilities do not provide a suitable boundary
- Update UI flow tests

**Steps:**

1. 保留现有“RDL 输入冲击响应”区块，另增“RDL 干预分析”区块，仅在当前结果含 I 时显示。
2. 展示 I 的 0/1 时间路径，避免把 I 的动态权重误称为路径。
3. 展示 I 的 RDL numerator/denominator/delay、动态权重和稳态增益，优先复用 Ts result 的 `distributed_lags`、`weights()`/`filter()`、`gain()` 和 `steady_state_gains`。
4. 计算历史样本的事实路径、无干预反事实路径和差异：在线性尺度使用 RDL filter 的贡献；对数模型将贡献作为 `delta_log_y`，反事实按 `factual / exp(delta_log_y)`，并展示相对变化百分比。状态空间初始化 burn-in 期间不做虚假结论，按现有 Ts 拟合值有效期掩码。
5. 图表只添加本功能所需的路径、事实/反事实和差异语义，不擅自添加其它参考线或视觉元素；表格与图必须来自同一组已对齐数组。

**Verification:** 使用确定性模拟数据检查直接效应和延迟效应的方向、长度、日期对齐；log=True 检查百分比计算；I-only 与 X+I 都能展示；普通 RDL 结果不出现空的干预区块。

### Task 8: 完整验证和交付检查

**Files:**

- No additional product files unless a test exposes a scoped defect

**Steps:**

1. 运行 HTFA RDL/SARIMAX focused suite：

   ```powershell
   Set-Location D:\HTFA_v1.1
   runtime\python.exe -m pytest -c tooling\pytest.ini tests\models\test_sarimax_modeling.py tests\models\test_sarimax_ui_flow.py tests\models\test_sarimax_boundaries.py -q
   ```

2. 运行共享数据概览测试，因为 common model input/state 可能影响共享 UI：

   ```powershell
   Set-Location D:\HTFA_v1.1
   runtime\python.exe -B -m pytest -c tooling\pytest.ini tests\ui_shared\data_overview -q
   ```

3. 运行 `python -m compileall` 覆盖本次改动目录，运行 `git diff --check`。
4. 检查 source Ts 与 HTFA runtime Ts 的导入版本、公开签名和中文选项到 enum 的一一映射。
5. 检查工作树只包含本功能正式文件和此前已存在的 `CONTEXT.md` 变更；不提交缓存、日志、数据库或临时导出。
6. 本轮不推送 HTFA，除非用户另行明确下达 push；如收到 push 指令，先运行 `tooling\scripts\clean_temps.ps1`，复核 `git status --short`，确认当前分支为 `main` 后再提交推送。

**Expected outcome:** RDL 页面可以完整配置并拟合历史干预分析，I 与 X 共同作用于 Y，I-only 也可用；invalid path 不会静默修正；普通 RDL、SARIMAX、ARDL 行为不回归；结果路径、动态响应和事实/反事实效果日期与数值一致。

## 当前待执行事项

- 本文件保存后等待用户选择执行方式；在收到执行确认前不修改上述业务代码。
- 执行时必须先完成 Tasks 1–3，再进入 HTFA Tasks 4–8。
- HTFA Streamlit 进程会缓存模块；完成代码同步后必须提醒用户重启 `scripts\start.bat`，单纯刷新页面不足以加载新 Ts/HTFA 模块。
