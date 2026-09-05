# Five-Domain Module Migration Implementation Plan

> **For Codex:** Execute this plan task-by-task with explicit verification at every phase boundary.

**Goal:** 将 HTFA 从现有 `dashboard/` 模块化单体迁移为五个内部领域模块，并明确分离经济工作簿协议与普通表格输入协议；通过逻辑 seam、直接切换、删除旧路径和完整回归验证，最终确认功能无退化。

> **Status:** 五领域迁移已完成；本计划中关于独立可移植组件的早期设想已由 ADR-0009 修正为 HTFA 内部的 `htfa.data.tabular` 与 `htfa.ui_shared.data_overview` 两个边界。以下旧路径仅保留为迁移历史，不是可用入口。

**Architecture:** 保留一个本地模块化单体和两个执行入口：应用入口负责交互式分析，数据维护入口负责 DuckDB 到 Excel 的发布。五个领域模块为 `data`、`monitoring`、`exploration`、`models/univariate`、`models/dfm`；`app`、`workspace`、`ui_shared`、`jobs` 是横向基础设施，不计入五个业务领域。依赖只能从领域 UI/适配器指向领域 core、共享契约和基础设施，不能反向依赖应用组装层、Streamlit 或其他领域的页面实现。

**Tech Stack:** Python 3.13 runtime、Streamlit、pandas、DuckDB、openpyxl、statsmodels、Ts、pytest、Streamlit `AppTest`、Windows `start.bat`。

---

## 0. 不可违反的迁移约束

1. 所有修改直接在本地 `main` 完成；每个阶段在提交前确认当前分支仍为 `main`，不创建分支，不使用 PR 分支。
2. 不保留任何迁移兼容层：不保留旧 import、旧 API、旧模块名、转发别名、deprecated wrapper、双写/双读、旧新路径并行、运行时探测回退或 feature flag。
3. 每次切换采用“先建立 seam → 迁移全部调用方 → 删除旧实现 → 静态扫描证明旧路径为零”的直接切换方式。旧路径删除前不得宣称该阶段完成。
4. “不回退”针对架构迁移路径和接口兼容策略；不得因此删除产品级数据安全行为。DuckDB→Excel 发布失败回滚、解析失败清空旧数据、输入校验和 fail-closed 是产品正确性，不是迁移兼容机制，必须保留并单独验证。
5. 业务语义不得因目录迁移改变：经济工作簿的指标白名单与 `0` 视为缺失规则、普通表格中的 `0` 语义、RDL 干预变量、SARIMAX/RDL/ARDL 的模型族差异、DFM 的独立性、工作区生命周期、handoff 快照和失败可见性都属于验收范围。
6. 每阶段只处理一个边界，阶段末必须有测试、静态依赖检查、运行时导入检查和可审阅的提交；测试失败时停在当前阶段，不用旧路径“救回”测试。

## 1. 当前基线与目标结构

### 1.1 已验证基线

基线取当前 `main` 的 `94de15b`，且本地 `main` 与 `origin/main` 同步，工作树干净。已执行：

- 主测试集：`573 passed, 97 warnings`。
- 独立组件测试：`74 passed`。
- 跨边界聚焦测试：`42 passed`。
- 当前 runtime 纯解析导入检查：`streamlit_loaded=False`、`data_overview_ui_loaded=False`、`dashboard_loaded=False`。

所有迁移阶段都以当前基线为比较对象，不以旧架构报告中 `eb6fe59` 的快照数字为准。

### 1.2 目标结构

```text
app.py                         # 应用组装入口
htfa/
  app/                         # 路由、页面组合、共享 UI 组装
  data/                        # 两种输入协议及经济数据领域规则
  monitoring/                  # 监测主题和报告组合
  exploration/                 # 自由探索和普通表格分析
  models/
    univariate/               # SARIMAX、RDL、ARDL 及其公共模型契约
    dfm/                       # DFM / Nowcasting
  workspace/                  # session workspace、页面快照、handoff
  ui_shared/                  # 纯共享渲染基础设施
  jobs/                       # 数据维护执行入口
htfa/data/tabular/            # 普通表格读取、解析和数据集契约
htfa/ui_shared/data_overview/ # 内部复用的 Streamlit 数据概览 UI
data/                         # 数据资产；DuckDB 为事实源，Excel 为快照
tests/                        # 领域和架构测试
scripts/ tooling/ runtime/   # 启动、工具链和项目运行时
```

### 1.3 依赖规则

允许的主依赖方向：

```text
app -> domain UI -> domain core -> shared contracts / workspace / ui_shared
jobs -> data publication contracts -> DuckDB / Excel writers
models/univariate -> models/common contracts -> Ts
models/dfm -> DFM numerical dependencies
monitoring -> data contracts + topic cores
exploration -> tabular input contract
```

禁止的方向：

- `data`、`monitoring`、`exploration`、`models` 的 core 导入 Streamlit、session state 或 `app`。
- 一个领域导入另一个领域的页面、renderer 或私有状态。
- `htfa.data.tabular` 不导入 Streamlit；`htfa.ui_shared.data_overview` 只向 UI 方向依赖普通表格能力。
- `jobs` 通过 UI 页面执行数据发布。
- DFM 通过 univariate workflow、SARIMAX 页面或模型库获得隐式耦合。
- 任何模块继续通过 `sys.path` 注入维持旧顶层包名。

## 2. 稳定 seam 与契约

迁移前先固定以下概念；实现时优先复用现有等价契约，不为“新目录”制造第二套业务对象。

### 2.1 输入协议

`htfa.data` 必须提供两个明确、不可混用的入口：

```python
class EconomicWorkbookReader(Protocol):
    def read(self, asset: FileAsset) -> EconomicWorkbookSnapshot: ...

class TabularInputSource(Protocol):
    def read(self, asset: FileAsset) -> TabularDataset: ...
```

- `EconomicWorkbookReader` 负责 UAE/经济工作簿的 sheet、指标字典、元数据和经济数据规则；非法指标或业务结构错误必须 fail-closed。
- `TabularInputSource` 负责普通用户表格的列、日期、变量和缺失值语义；数值 `0` 必须保持为 `0`，不能套用经济工作簿的 `0`-as-missing 规则。
- 两者可以共享字节读取、编码识别、日期解析等基础函数，但不能共享一个包含经济业务语义的“万能 parser”。
- seam 的失败契约必须一致：新数据未完整通过校验时，调用方不得继续使用旧数据，也不得静默回退到另一种协议。

### 2.2 数据身份与结果状态

保留现有 `TabularDataset`/数据源的身份和 fingerprint 语义，统一在 `htfa.data` 定义或重导出后的唯一位置；任何变更都必须使旧结果失效。监测主题使用显式结果状态，而非通过父 renderer 是否抛错来表达：

```python
class TopicResult(Protocol):
    topic: str
    status: Literal["ok", "empty", "failed"]
    payload: object | None
    error: str | None
```

`failed` 只表示该主题失败；报告组合器必须继续处理其余主题，并在 UI 中显示可追踪的错误信息。

### 2.3 模型契约

继续使用当前无 Streamlit/Ts 结果类型的 `ModelAdapter`、`ModelWorkflow`、`ForecastContext`、`ForecastRequest`、`ForecastResult`、诊断视图等契约作为迁移锚点。公共 workflow 只承载跨模型生命周期，不吞掉族特定语义；SARIMAX、RDL、ARDL 的 result view 和不支持的结果选择继续分别验证。DFM 使用自己的领域契约，不接入 univariate 模型库。

### 2.4 Workspace 与共享 UI

`workspace` 只负责文件资产、页面快照、handoff 和生命周期，不依赖 Streamlit。`ui_shared` 只放跨领域的渲染基础设施、错误展示和图例/Matplotlib 辅助，不放领域业务计算。应用组装层负责把领域页面接到导航和入口，不成为领域 core 的依赖。

## 3. 分阶段执行

### 阶段 A：冻结决策、术语和架构门禁

**目的：** 把已确认的五模块、两种输入协议、直接切换和“无兼容/无迁移回退”写成仓库内可执行规则。

**文件：**

- 修改 `D:/HTFA_v1.1/CONTEXT.md`：补充五个领域模块、两个输入协议、seam、直接切换、旧路径删除和“产品安全回滚不等于兼容回退”的术语。
- 新建 `D:/HTFA_v1.1/docs/adr/0006-five-domain-modular-monolith.md`：记录目标模块、依赖方向和模块不等于导航 tab。
- 新建 `D:/HTFA_v1.1/docs/adr/0007-economic-workbook-and-tabular-input-seams.md`：记录两种输入协议及 `0` 语义差异。
- 新建 `D:/HTFA_v1.1/docs/adr/0008-direct-cutover-without-migration-compatibility.md`：记录直接切换、删除旧路径、禁止 alias/wrapper/fallback/dual path，以及保留数据安全回滚的边界。
- 新建 `D:/HTFA_v1.1/tests/architecture/test_migration_rules.py`：检查目标目录、禁止依赖和禁止兼容符号的静态规则。

**执行与验收：**

1. `git branch --show-current` 必须输出 `main`；`git status --short` 必须只显示本阶段文档和测试。
2. 用 `rg` 建立迁移前基线：所有 `dashboard.` 生产导入、`dashboard/preview`、`data/UAE/scripts` 调用点和 `sys.path` 注入点都登记到计划/测试中。
3. 运行 `runtime\\python.exe -B -m pytest -c tooling\\pytest.ini tests\\architecture -q`，新门禁先通过。
4. 提交：`docs(architecture): define five domain migration boundaries`。

**阶段产物：** ADR、术语、静态门禁和迁移前依赖清单。此阶段不移动代码。

### 阶段 B：建立并完成 data 输入 seam

**目的：** 先处理报告指出的最关键边界，把经济工作簿和普通表格输入彻底拆开，并让所有调用方一次性切到新 seam。

**文件范围：**

- 新建 `D:/HTFA_v1.1/htfa/data/`，按 `contracts.py`、`economic_workbook.py`、`tabular_input.py`、`dataset.py`、`identity.py` 拆分职责。
- 将 `D:/HTFA_v1.1/dashboard/preview/` 的完整经济工作簿能力（`core`、`domain`、`modules`、`shared`，包括 loader、计算、summary 导出、renderer、tabs 和 plotting）迁移到 `htfa/data/economic_workbook/`；其中纯规则与 UI 适配分离，保留已验证的白名单、元数据和缺失值规则。
- 修改探索、模型输入和共享数据概览 UI 的适配配置，让探索和模型输入显式使用 `TabularInputSource`。
- 修改 UAE 监测和数据服务调用方，让经济工作簿只经过 `EconomicWorkbookReader`。
- 移动并改写相关测试到 `D:/HTFA_v1.1/tests/data/`、`D:/HTFA_v1.1/tests/exploration/` 和 `D:/HTFA_v1.1/tests/ui_shared/data_overview/`。
- 删除整个 `dashboard/preview/` 旧实现和任何只为旧路径服务的转发文件；全仓不得出现旧 import。

**执行与验收：**

1. 先写 seam 测试：经济工作簿 whitelist/元数据/`0`-as-missing、普通表格 `0` 保留、日期和缺失值、身份 fingerprint、解析失败清空旧数据。
2. 用 runtime 执行纯导入检查：导入 `htfa.data` 和普通表格 parser 后，`streamlit`、`htfa.app`、旧 `dashboard` 均不得进入 `sys.modules`。
3. 用 `rg` 检查生产代码不再导入 `dashboard.preview`；禁止加入 fallback 分支或兼容名称。
4. 运行 data、exploration、model-input、component 相关测试，再运行主套件。
5. 提交：`refactor(data): split economic and tabular input seams`。

**阶段出口：** 两种协议均有唯一入口；没有“先经济 parser，失败后普通 parser”或反向行为；旧 preview parser 不存在。

### 阶段 C：迁移 app 组装、workspace 和 ui_shared

**目的：** 去掉 `dashboard` 作为事实上的根命名空间和 `sys.path` 注入，把应用组装与共享基础设施从领域代码中剥离。

**文件范围：**

- 将 `D:/HTFA_v1.1/dashboard/core/workspace/` 迁移至 `D:/HTFA_v1.1/htfa/workspace/`，保持 workspace、snapshot、handoff 生命周期语义。
- 将 `D:/HTFA_v1.1/dashboard/core/ui/` 中真正跨领域的图例、Matplotlib、错误展示和共享组件迁移至 `D:/HTFA_v1.1/htfa/ui_shared/`。
- 将路由、导航、页面组合和共享 Streamlit 组装逻辑迁移至 `D:/HTFA_v1.1/htfa/app/`。
- 修改 `D:/HTFA_v1.1/app.py`、`D:/HTFA_v1.1/scripts/run_htfa.py`、`D:/HTFA_v1.1/scripts/start.bat` 和 `D:/HTFA_v1.1/tooling/pytest.ini` 使用新顶层包。
- 将数据概览从旧独立组件实现直接切换到 `htfa.data.tabular` 与 `htfa.ui_shared.data_overview`；不建立独立安装入口或兼容包。
- 删除 `app.py` 的 `components` 路径注入和测试配置中的旧路径注入，前提是组件已通过明确的项目运行时安装方式可导入；不得用另一条隐式注入替代。
- 删除旧 `dashboard/core/workspace`、旧共享 UI 转发层和旧组装入口。

**执行与验收：**

1. 运行 workspace、navigation、component import boundary、AppTest 基线。
2. 运行 `runtime\\python.exe -m compileall -q app.py htfa components`。
3. 用 `inspect` 检查 workspace 和 shared UI 的公共入口只存在于新路径。
4. 从干净 Python 进程导入 `htfa.app`、`htfa.workspace`、`htfa.data.tabular`；纯数据导入不得加载 Streamlit。
5. 提交：`refactor(app): move session infrastructure and composition shell`。

**阶段出口：** 应用入口、workspace、共享 UI 有唯一实现；`dashboard.core` 不再是公共根；启动脚本不依赖兼容 import。

### 阶段 D：迁移 monitoring 并拆开主题失败边界

**目的：** 将监测作为一个领域，但让每个主题独立失败，避免油价主题成为政府金融、房地产和交通主题的控制流父节点。

**文件范围：**

- 将 `D:/HTFA_v1.1/dashboard/analysis/industrial/`、`D:/HTFA_v1.1/dashboard/analysis/uae/` 迁移至 `D:/HTFA_v1.1/htfa/monitoring/`。
- 新建 `htfa/monitoring/contracts.py`、`report.py` 和主题级 core/UI 结构。
- 修改 `D:/HTFA_v1.1/dashboard/analysis/uae/oil/renderer.py`：油价 renderer 只负责油价主题；政府金融、房地产、交通由 report composer 分别调用。
- 将 `services.py` 中的业务计算与 renderer 组装职责分开，保持数据契约和图表语义不变。
- 迁移监测测试，新增单主题成功、空数据、失败和其他主题继续渲染的组合测试。

**执行与验收：**

1. 测试油价失败时政府金融/房地产/交通仍执行；每个主题返回 `ok/empty/failed` 状态。
2. AppTest 验证 UAE 宏观、高频主题和工业监测页面在单主题失败时仍能展示剩余主题及错误信息。
3. 检查 renderer 之间不存在父子隐式调用；组合顺序由 `report.py` 明确声明。
4. 运行 monitoring 相关测试和主套件。
5. 提交：`refactor(monitoring): compose independent domain topics`。

**阶段出口：** 主题并行组合、失败隔离和错误可见性均由测试证明；无以旧 renderer 路径为入口的兼容层。

### 阶段 E：迁移 exploration

**目的：** 将自由探索作为独立领域，明确它使用普通表格协议，不借用经济工作簿业务规则。

**文件范围：**

- 将 `D:/HTFA_v1.1/dashboard/explore/` 迁移至 `D:/HTFA_v1.1/htfa/exploration/`，保持 core、UI adapter、DTW、lead-lag 和频率对齐语义。
- 更新探索数据源，使其只依赖 `TabularInputSource` 和新的 dataset identity 契约。
- 迁移 `D:/HTFA_v1.1/tests/explore/` 到新领域测试位置，删除旧路径下的测试和导入。

**执行与验收：**

1. 普通表格中真实的 `0`、干预变量、日期列和变量选择均做断言。
2. 检查探索 core 在无 Streamlit 环境中可导入和运行。
3. AppTest 验证数据变更会隐藏旧结果，且不读取经济工作簿 whitelist。
4. 运行 exploration、data seam、AppTest 和主套件。
5. 提交：`refactor(exploration): move free-analysis domain behind data seam`。

**阶段出口：** exploration 只使用普通表格协议；旧 `dashboard.explore` 不存在。

### 阶段 F：迁移 models/univariate，保留模型族语义但不保留旧路径

**目的：** 把当前已经存在的公共 workflow/adapter/result view 组织为 univariate 领域，并显式隔离 SARIMAX、RDL、ARDL 的族特定行为。

**文件范围：**

- 将 `D:/HTFA_v1.1/dashboard/models/common/` 迁移到 `D:/HTFA_v1.1/htfa/models/univariate/common/`。
- 将 `D:/HTFA_v1.1/dashboard/models/SARIMAX/core/` 与 UI 迁移到 `htfa/models/univariate/sarimax/`，并将 RDL、ARDL 的族特定代码拆入对应目录；公共模型库留在 univariate common。
- 将 `sarimax_page.py`、`standalone_model.py`、state 和 pages 重新接到 `htfa.app` 与 `htfa.workspace`，不保留旧 standalone URL/API 或旧导入别名。
- 保留并迁移 `ModelAdapter`、`ModelWorkflow`、`ModelingInput`、forecast/diagnostic view 等契约；删除仅为旧命名空间存在的薄转发模块。
- 迁移模型测试并新增族边界测试：不支持的结果选择继续显式报错，RDL 干预变量不被普通 SARIMAX 路径吞掉，模型库不接 DFM。

**执行与验收：**

1. 先执行静态签名检查，确认 UI 控件、workflow、adapter、Ts 调用参数一一对应；本阶段不改变统计参数和默认值。
2. 分别验证 SARIMAX、RDL、ARDL 的 fit、diagnostics、forecast、evaluation、invalidations、handoff 和 standalone 页面。
3. AppTest 覆盖至少：普通 SARIMAX、RDL intervention、ARDL、模型库、独立模型页、数据变更清理旧结果。
4. 用数值对比检查拟合值、残差、预测均值、区间、方差和评价窗口，不只检查页面渲染成功。
5. 运行模型相关测试、component 测试和主套件。
6. 提交：`refactor(models): migrate univariate families without compatibility paths`。

**阶段出口：** univariate 领域唯一入口已生效，三族语义和现有数值行为无变化，`dashboard.models` 旧命名空间不存在。

### 阶段 G：迁移 models/dfm

**目的：** 将 DFM/Nowcasting 作为第五个独立领域完成迁移，避免由 univariate 公共 workflow 或页面组合器提供隐式依赖。

**文件范围：**

- 将 `D:/HTFA_v1.1/dashboard/models/DFM/` 迁移至 `D:/HTFA_v1.1/htfa/models/dfm/`，按 preparation、training、results、decomposition 和 UI 组织。
- 明确 DFM 自己的数据准备、拟合结果、预测和分解契约；仅共享 workspace、ui_shared 和基础数据身份能力。
- 迁移 DFM 测试，删除旧导入和旧目录。

**执行与验收：**

1. 运行 DFM core 无 Streamlit 导入检查。
2. AppTest 覆盖 DFM 数据输入、训练、结果、分解、预测和错误状态。
3. 静态检查 DFM 不依赖 `models.univariate` 的页面、workflow 或模型库；如共享契约需要移动，移动到真正的基础契约模块，不做反向兼容。
4. 运行 DFM 相关测试和主套件。
5. 提交：`refactor(dfm): move nowcasting domain without univariate coupling`。

**阶段出口：** 五个领域均已有唯一实现；DFM 与 univariate 的边界由 import 检查和 AppTest 证明。

### 阶段 H：迁移 jobs，保持数据发布链的唯一事实源

**目的：** 将数据维护脚本纳入 `htfa.jobs`，但保持数据资产位置、DuckDB 权威性和 Excel 快照发布流程不变。

**文件范围：**

- 将 `D:/HTFA_v1.1/data/UAE/scripts/` 中的业务脚本整理至 `D:/HTFA_v1.1/htfa/jobs/uae_data/`；数据资产仍留在 `D:/HTFA_v1.1/data/UAE/`。
- 修改 `D:/HTFA_v1.1/scripts/start.bat`、维护入口和测试配置，改为显式项目根/数据根参数；不保留旧脚本 wrapper。
- 保留 `update_data.py` 的来源级失败隔离，保留 `merge_workbook.py` 的 DuckDB→Excel 单向发布和写表失败安全行为。
- 所有新增数据变量仍必须先入 `data/UAE/uae.duckdb`，再由 merge 更新 `data/UAE/阿联酋.xlsx`；禁止直接从来源写指标到 Excel。

**执行与验收：**

1. 运行脚本静态检查，确认不存在硬编码旧工作目录和旧 import。
2. 使用临时副本验证：来源失败不会阻断其他来源；DuckDB 更新失败不会产生错误 Excel；Excel 写入失败保留可恢复的原快照。
3. 验证指标字典仍由 merge 同步，不手工维护单指标。
4. 运行 data contract、job、UAE 分析和主套件。
5. 提交：`refactor(data): move UAE maintenance jobs behind database publication boundary`。

**阶段出口：** jobs 只有新入口；数据事实源与发布链未改变；产品安全回滚被保留并有专门测试。

### 阶段 I：最终删除旧架构并完成零遗留门禁

**目的：** 证明迁移是完成态，而不是新旧架构并存。

**删除与检查：**

- 删除 `D:/HTFA_v1.1/dashboard/` 全目录中剩余的生产实现和测试，只保留明确无用的空目录不进入提交。
- 删除所有旧 API、旧模块名、兼容 alias、wrapper、双路径配置、旧路径文档示例和临时迁移开关。
- 新增或收紧 `D:/HTFA_v1.1/tests/architecture/test_no_legacy_paths.py`，对源码、测试、启动脚本、配置和文档做零命中断言；允许的历史 ADR 记录需使用明确的历史文本格式，不得成为可导入路径。

**最终验收命令：**

```powershell
git branch --show-current
git status --short
runtime\python.exe -B -m pytest -c tooling\pytest.ini tests -q
runtime\python.exe -B -m pytest -c tooling\pytest.ini tests\data\tabular tests\ui_shared\data_overview -q
runtime\python.exe -B -m compileall -q app.py htfa
rg -n "dashboard\.|dashboard/|dashboard\\|from dashboard|import dashboard|components\.data_overview|from data_overview|import data_overview|sys\.path.*components" app.py htfa scripts tooling tests
```

`rg` 结果必须只允许测试规则本身、ADR 的历史决策文字和必要的安全 rollback 术语；不得出现可执行旧路径、兼容入口或 fallback 分支。若仓库规范要求对关键词采用更精确的白名单，则在测试中按 AST/import 语义检查，不能通过简单删词掩盖旧路径。

**最终回归矩阵：**

1. 主测试集和组件测试达到或超过当前基线，且没有因跳过测试、删除断言或放宽校验而达成。
2. AppTest 覆盖两个入口、五个领域、模型库、standalone/handoff、数据变更后的状态清理、监测单主题失败隔离和数据维护失败可见性。
3. 每个领域 core 在独立进程中导入，确认不加载不必要的 Streamlit/UI/其他领域页面。
4. 对关键模型和图表做语义验证：表格与图表来自相同数据数组；预测数值、区间、方差、评价窗口和模型族差异与基线一致。
5. 运行时从 `runtime` 导入新包，确认不是从开发机其他位置误导入；启动 `scripts\start.bat`，等待服务 ready 后访问主要用户流程。
6. 对数据发布链执行 DuckDB 权威性、Excel 快照、指标字典、失败恢复和禁止直接写指标数据检查。
7. 汇总迁移前后测试结果、静态扫描结果、import matrix、AppTest 流程、关键数值对比和 warning 分类；新增 warning 不得被静默吞掉。
8. 最终确认 `main`、`origin/main` 和工作树状态；只有正式源文件进入提交，不提交 runtime 缓存、数据库 WAL、临时导出和用户数据。
9. 提交：`refactor(architecture): remove legacy dashboard namespace`。

## 4. 完成定义

只有同时满足以下条件才报告“完全迁移并确认功能无退化”：

- 五个领域目录存在且各自有明确 core/UI 边界：`htfa/data`、`htfa/monitoring`、`htfa/exploration`、`htfa/models/univariate`、`htfa/models/dfm`。
- 经济工作簿与普通表格是两个显式协议；`0`、whitelist、元数据和 fail-closed 语义均经过测试。
- `dashboard/`、旧独立组件目录、顶层 `data_overview`、旧 import、旧 API、wrapper、alias、双路径和迁移 fallback 均不存在。
- 应用入口与 jobs 入口均只使用新路径；纯 core 导入边界成立。
- 所有主要用户流程、模型数值、图表语义、workspace/handoff、监测失败隔离和数据安全行为均验证通过。
- 测试不低于基线：主套件至少 `573 passed` 的量级并逐项解释变化；组件至少 `74 passed` 的量级；任何减少都必须先补齐等价覆盖，不能以删除测试解决。
- 最终提交前 `git branch --show-current` 为 `main`，本地与远端关系已核对，工作树无未预期文件。

完成迁移后必须重启 `D:/HTFA_v1.1/scripts/start.bat`，因为 Streamlit 进程会缓存模块；刷新页面不足以证明新架构已加载。

## 5. 每阶段交接模板

每个阶段结束时记录：

```text
阶段：A/B/C/D/E/F/G/H/I
提交：<commit>
变更范围：<生产文件、测试、文档>
已删除旧路径：<列表>
测试：<命令与结果>
静态边界：<rg/AST/import 结果>
运行时验证：<runtime/AppTest/关键用户流程>
未决问题：<必须为零；否则不得进入下一阶段>
```

任何阶段如果只能通过旧路径、兼容别名或回退分支恢复测试，阶段状态为失败，必须修复新 seam 后再继续；不允许带病进入下一阶段。
