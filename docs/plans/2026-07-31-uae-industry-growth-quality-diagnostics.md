# UAE Industry Growth Quality Diagnostics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在“行业分析”Tab中增加行业扩张广度、增长集中度和增长持续性/状态矩阵，全部只使用现有16个行业季度不变价GDP与非油实际GDP。

**Architecture:** 扩展现有纯计算边界 `dashboard.analysis.uae.growth`，复用 `ContributionResult` 的16行业增长贡献，集中生成广度、集中度和持续性结果；`services.py` 只负责装配结果，`charts.py` 只负责三个专用Plotly图，`renderer.py` 只按稳定组名路由。缺失季度不压缩、不缩小行业分母、不插值；统计不可解释时保留 `NaN`，不截断或填0。

**Tech Stack:** Python 3.11+、pandas、NumPy、Plotly、Streamlit、pytest、Streamlit AppTest、Ruff

---

## 1. 已确认的数据与统计口径

### 1.1 数据边界

- 数据：16个非油行业季度不变价GDP，以及非油实际GDP。
- 水平值覆盖：2012Q1–2025Q4。
- 同比增速覆盖：2013Q1–2025Q4，共52个季度。
- 16行业水平值逐季加总等于非油实际GDP，当前最大比例误差低于 `1e-8`。
- 新功能不依赖行业现价GDP；现价数据只继续服务既有“行业量价四象限图”。

### 1.2 基础量

对行业 `i`、季度 `t`：

```text
g_i,t = 100 * (Y_i,t / Y_i,t-4 - 1)
s_i,t-4 = Y_i,t-4 / Y_nonoil,t-4
c_i,t = s_i,t-4 * g_i,t
g_nonoil,t = sum_i(c_i,t)
```

- `Y` 为不变价增加值。
- 所有加权诊断统一使用上年同期权重 `s_i,t-4`，与同比贡献核算一致。
- 每个可计算季度必须验证 `sum_i(s_i,t-4) == 1`。
- 必须复用 `calculate_growth_contributions`；不得在服务层建立第二套贡献公式。

### 1.3 扩张广度

四个条件分别计算不加权与加权比例：

1. 正增长：`g_i,t > 0`。
2. 高于自身历史均值：`g_i,t > expanding_mean(g_i, <= t-1)`。
3. 较上季度加快：`g_i,t > g_i,t-1`，比较的是同比增速的季度变化。
4. 连续四季度正增长：`g_i,t, g_i,t-1, g_i,t-2, g_i,t-3 > 0`。

```text
D_k,t = 100 / N * sum_i I(condition_k,i,t)
WD_k,t = 100 * sum_i s_i,t-4 * I(condition_k,i,t)
```

历史均值必须：

- 排除当季，防止前视和机械自包含；
- 使用扩展窗口；
- 至少有8个历史同比季度后才计算，最早为2015Q1。

缺失规则：

- 分母固定为16个行业；
- 任一行业当季条件不可计算，则该季度对应广度指标为 `NaN`；
- 不得按“有效行业数”缩小分母。

“广泛扩张/结构性扩张/高度集中”的80%与50%阈值只解释“正增长行业比例”，不套用到其余三条广度线。

### 1.4 增长集中度

#### 前三行业净增长覆盖率

忠实保留用户提出的净增长分母：

```text
CR3_net,t = 100 * sum(top 3 max(c_i,t, 0)) / g_nonoil,t
```

边界必须显式保留：

- `g_nonoil,t <= 0`：结果为 `NaN`；
- 正向行业少于3个：对现有正向行业求和；
- 允许超过100%，因为负贡献可能抵消部分正贡献；
- 不截断到100%，不改用绝对贡献。

真实样本中该指标有8个季度超过100%，另有6个非油增长非正季度不可解释。图例和方法说明必须把它命名为“净增长覆盖率”，避免误读成有界市场份额。

#### 正向贡献HHI

```text
p_i,t = max(c_i,t, 0) / sum_j max(c_j,t, 0)
HHI_t = sum_i p_i,t^2
effective_industries_t = 1 / HHI_t
```

- 没有正贡献时，HHI与有效行业数均为 `NaN`。
- HHI保留0–1尺度；有效行业数用于悬浮解释，不单独占一个子图。

#### 行业增速离散度

用户给出的公式是加权方差：

```text
V_t = sum_i s_i,t-4 * (g_i,t - g_nonoil,t)^2
```

后台同时保留：

```text
weighted_variance = V_t
weighted_std = sqrt(V_t)
```

图表展示 `weighted_std`，单位为百分点；`weighted_variance` 保留在结果中用于复核，不把平方百分点误标为百分比。

### 1.5 增长持续性与状态

每个行业、每个可计算季度生成：

- `当前实际增加值增速`；
- `最近4季度平均增速`：包含当季；
- `最近8季度平均增速`：包含当季；
- `连续正增长季度数`：从当季向后连续计数，不设人为上限；
- `最近8季度高于自身历史趋势次数`：0–8；
- `当季增速减过去4季度均值`：过去4季度不含当季；
- `当季增速减历史趋势`；
- `当季增速减上季度增速`；
- `当季行业实际GDP占非油实际GDP比例`；
- `行业状态`。

状态定义：

| 状态 | 水平条件 | 动量条件 |
|---|---|---|
| 高位加速 | 当季增速高于截至上季的扩展历史均值 | 当季同比高于上季度同比 |
| 高位放缓 | 当季增速高于历史均值 | 当季同比不高于上季度同比 |
| 低位改善 | 当季增速不高于历史均值 | 当季同比高于上季度同比 |
| 低位恶化 | 当季增速不高于历史均值 | 当季同比不高于上季度同比 |

## 2. 页面设计

在现有行业分析三张图之后增加：

1. **行业扩张广度指数**
   - 同时显示四条广度线；
   - Plotly按钮切换“不加权”与“按上年同期行业权重加权”；
   - 纵轴固定0–100%；
   - 对“正增长行业比例”解释50%与80%阈值；
   - 不增加Streamlit运行按钮，不产生陈旧结果状态。

2. **行业增长集中度**
   - 三个纵向子图，共享季度轴；
   - 子图1：前三行业净增长覆盖率，允许超过100%和断点；
   - 子图2：正向贡献HHI，范围0–1，悬浮显示有效行业数；
   - 子图3：行业加权增速标准差，单位百分点；
   - 不使用双轴，不把不同量纲压到同一条纵轴。

3. **行业增长持续性与状态矩阵**
   - 默认显示最新可计算季度；
   - 横轴：当季增速减历史趋势；
   - 纵轴：当季同比增速减上季度同比增速；
   - 零线形成四个状态象限；
   - 气泡面积：当季行业实际GDP占非油实际GDP比例；
   - 颜色：四种状态；
   - 行业名称直接显示或在空间不足时保留悬浮标签；
   - 悬浮展示全部持续性字段；
   - 显示醒目季度徽标。

不在本轮增加第二套动画框架或新的Streamlit状态控件。若后续需要状态矩阵跨期播放，应先抽取既有四象限图的通用动画构造器，再单独实施。

## 3. 结果契约

在 `dashboard/analysis/uae/growth.py` 增加：

```python
@dataclass(frozen=True)
class IndustryDiagnosticsResult:
    contribution_result: ContributionResult
    growth_rates: pd.DataFrame
    base_year_shares: pd.DataFrame
    current_shares: pd.DataFrame
    breadth: pd.DataFrame
    concentration: pd.DataFrame
    persistence: pd.DataFrame


def calculate_industry_diagnostics(
    total: pd.Series,
    components: Mapping[str, pd.Series],
    *,
    periods: int = 4,
    history_min_periods: int = 8,
    persistence_window: int = 8,
    absolute_tolerance: float = 1e-5,
    relative_tolerance: float = 1e-10,
) -> IndustryDiagnosticsResult:
    ...
```

`breadth` 使用扁平稳定列名：

```text
不加权｜正增长行业比例
不加权｜增速高于历史均值的行业比例
不加权｜增速较上季度加快的行业比例
不加权｜连续四季度正增长的行业比例
加权｜正增长行业比例
加权｜增速高于历史均值的行业比例
加权｜增速较上季度加快的行业比例
加权｜连续四季度正增长的行业比例
```

`concentration` 列：

```text
前三行业净增长覆盖率
正向贡献HHI
正向贡献有效行业数
加权增速方差
加权增速标准差
```

`persistence` 索引为 `[季度, 行业]`，列名使用第1.5节的中文名称。

---

### Task 1: 锁定纯计算统计契约

**Files:**
- Modify: `tests/analysis/uae/test_growth.py`
- Modify: `dashboard/analysis/uae/growth.py:12-192`

**Step 1: 写广度失败测试**

构造4个行业、至少12个连续季度的合成水平值，使用较短的测试参数：

```python
result = calculate_industry_diagnostics(
    total,
    components,
    periods=1,
    history_min_periods=3,
    persistence_window=4,
)

expected_unweighted = conditions.mean(axis=1) * 100
expected_weighted = (
    result.base_year_shares.where(conditions).sum(axis=1) * 100
)
pd.testing.assert_series_equal(
    result.breadth["不加权｜正增长行业比例"],
    expected_unweighted,
)
pd.testing.assert_series_equal(
    result.breadth["加权｜正增长行业比例"],
    expected_weighted,
)
```

同时断言历史均值使用 `shift(1).expanding(...)`，当季数据不能进入自身历史基准。

**Step 2: 写集中度边界失败测试**

使用贡献 `[6, 4, 2, -4]`、净增长 `8` 的合成季度，断言：

```python
assert cr3_net == pytest.approx(150.0)
assert cr3_net > 100
```

再构造净增长非正季度，断言CR3为 `NaN`；构造无正贡献季度，断言HHI为 `NaN`。

**Step 3: 写离散度失败测试**

```python
expected_variance = (
    weights * growth.sub(total_growth, axis=0).pow(2)
).sum(axis=1)
pd.testing.assert_series_equal(
    result.concentration["加权增速方差"],
    expected_variance,
)
pd.testing.assert_series_equal(
    result.concentration["加权增速标准差"],
    np.sqrt(expected_variance),
)
```

**Step 4: 写持续性与状态失败测试**

分别覆盖四种状态，并断言：

- 4/8季度均值窗口；
- 过去4季度均值排除当季；
- 连续正增长在遇到0、负值或缺失时终止；
- 最近8季度高于历史趋势次数范围为0–8。

**Step 5: 写缺失与时间索引失败测试**

- 缺少一个中间季度：抛出“季度索引必须连续”；
- 任一行业某季度缺失：该季度诊断保留 `NaN`，不删除季度；
- 权重和偏离1超过容差：抛出明确错误；
- 行业列少于1列、重复季度、非递增索引：抛出明确错误。

**Step 6: 运行测试确认失败**

Run:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/analysis/uae/test_growth.py -p no:cacheprovider --basetemp C:\tmp\htfa_industry_diagnostics_red -q
```

Expected: FAIL，缺少 `IndustryDiagnosticsResult` 和 `calculate_industry_diagnostics`。

**Step 7: 实现最小纯计算逻辑**

- 复用 `_align_components` 与 `calculate_growth_contributions`；
- 验证季度连续性后再执行位置型 `shift`；
- 不调用Streamlit、Plotly或工作簿解析器；
- 保留现有 `calculate_diffusion` API与测试。

**Step 8: 运行纯计算测试**

Run: 上述命令。

Expected: `tests/analysis/uae/test_growth.py` 全部通过。

---

### Task 2: 接入真实工作簿服务结果

**Files:**
- Modify: `dashboard/analysis/uae/services.py:243-442`
- Modify: `tests/analysis/uae/test_services.py:158-246`

**Step 1: 写真实数据集成失败测试**

```python
panel = build_growth_panel(
    load_runtime_uae_bundle(DEFAULT_UAE_WORKBOOK)
)
assert {
    "行业扩张广度指数",
    "行业增长集中度",
    "行业增长持续性与状态矩阵",
}.issubset(panel.series_groups)
```

对真实样本断言：

- 同比季度为2013Q1–2025Q4，共52期；
- 最新正增长行业比例约93.75%；
- 最新加权正增长广度约99.279%；
- 最新加权加速广度约66.926%；
- 最新CR3净增长覆盖率约56.236%；
- 最新HHI约0.133877；
- 最新加权增速标准差约3.258837个百分点；
- 最新状态数量为：高位加速6、高位放缓3、低位改善2、低位恶化5。

真实值断言使用合理容差，不依赖显示格式。

**Step 2: 运行测试确认失败**

Run:

```powershell
python -m pytest tests/analysis/uae/test_services.py -p no:cacheprovider --basetemp C:\tmp\htfa_industry_service_red -q
```

Expected: FAIL，三个新组尚不存在。

**Step 3: 最小接入**

```python
diagnostics = calculate_industry_diagnostics(
    quarterly_nonoil["非油实际GDP"],
    {
        column: quarterly_nonoil[column]
        for column in industry_series
    },
    periods=4,
    absolute_tolerance=1e-5,
    relative_tolerance=1e-10,
)
industry_contributions = diagnostics.contribution_result
```

- 用 `diagnostics.contribution_result` 替代当前重复的贡献调用；
- 现有前5行业拉动图继续使用同一 `contributions`；
- 将三个结果表加入 `series_groups`；
- 新功能只增加 `REAL_INDUSTRY_IDS` 的派生使用，不新增来源ID；
- 添加方法说明，明确CR3>100、非正增长季度缺失、历史均值无前视、离散度单位。

**Step 4: 运行服务测试**

Expected: 服务测试全部通过，现有行业拉动与量价四象限结果不变。

---

### Task 3: 实现行业扩张广度图

**Files:**
- Modify: `dashboard/analysis/uae/charts.py:1-713`
- Modify: `tests/analysis/uae/test_renderer.py:23-205`

**Step 1: 写失败测试**

```python
figure = build_industry_breadth_figure(frame, title="行业扩张广度指数")
assert len(figure.data) == 8
assert [button.label for button in figure.layout.updatemenus[0].buttons] == [
    "不加权",
    "按上年同期行业权重加权",
]
assert figure.layout.yaxis.range == (0, 100)
```

断言默认只显示不加权四条线，加权四条线由Plotly按钮切换；50%与80%参考线存在。

**Step 2: 运行专项测试确认失败**

Run:

```powershell
python -m pytest tests/analysis/uae/test_renderer.py -k breadth -q
```

Expected: FAIL，图表构造器不存在。

**Step 3: 实现图表**

新增：

```python
def build_industry_breadth_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    max_points: int = 80,
) -> go.Figure:
    ...
```

- 统一0–100%纵轴；
- 年度Q4刻度；
- 四条线颜色跨加权模式保持一致，线型区分模式；
- 按钮只改变trace可见性，不触发Streamlit重算；
- 悬浮显示季度、指标、比例和权重口径。

**Step 4: 运行专项测试**

Expected: PASS。

---

### Task 4: 实现增长集中度图

**Files:**
- Modify: `dashboard/analysis/uae/charts.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Step 1: 写失败测试**

断言：

- 使用三个纵向子图且共享季度轴；
- CR3保留 `NaN` 断点和150%样本值，不截断；
- HHI纵轴范围为0–1；
- 标准差纵轴标题为“百分点”；
- HHI悬浮数据包含有效行业数。

**Step 2: 实现**

```python
def build_industry_concentration_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    max_points: int = 80,
) -> go.Figure:
    ...
```

使用 `plotly.subplots.make_subplots(rows=3, cols=1, shared_xaxes=True)`。不得用归一化或双轴掩盖量纲差异。

**Step 3: 运行专项测试**

Run: `python -m pytest tests/analysis/uae/test_renderer.py -k concentration -q`

Expected: PASS。

---

### Task 5: 实现持续性与状态矩阵

**Files:**
- Modify: `dashboard/analysis/uae/charts.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Step 1: 写失败测试**

构造四个行业分别落入四种状态，断言：

- 四条状态trace及固定状态颜色；
- 横纵零线各一条；
- 四个状态标签存在；
- 最新季度徽标存在；
- marker面积来自行业占比；
- hover包含4/8季均值、连续正增长、高于趋势次数、相对过去4季变化。

**Step 2: 实现**

```python
def build_industry_state_matrix_figure(
    frame: pd.DataFrame,
    *,
    title: str,
) -> go.Figure:
    ...
```

- 只读取最新完整季度；
- 坐标范围必须包含0并留白；
- 状态颜色固定，不使用行业颜色；
- 行业名称优先直接标注；若Plotly布局测试显示严重遮挡，可退回悬浮标签，但不得隐藏行业识别信息。

**Step 3: 运行专项测试**

Run: `python -m pytest tests/analysis/uae/test_renderer.py -k state_matrix -q`

Expected: PASS。

---

### Task 6: 接入行业分析Tab并更新文档

**Files:**
- Modify: `dashboard/analysis/uae/renderer.py:10-126`
- Modify: `tests/analysis/uae/test_renderer.py:219-286`
- Modify: `docs/analysis/阿联酋经济监测变量字典.md`

**Step 1: 写路由失败测试**

- `GROWTH_INDUSTRY_GROUPS` 在现有三组之后包含三个新组；
- AppTest行业分析Tab中的Plotly元素由3个增至6个；
- 页面没有新增原始DataFrame、运行按钮或第二个工作簿解析器。

**Step 2: 更新图表路由**

在 `_render_panel` 中按稳定组名路由到三个专用构造器。路由顺序：

```text
GDP部门拉动与石油产量同比
非油实际GDP同比及行业拉动
行业量价四象限图
行业扩张广度指数
行业增长集中度
行业增长持续性与状态矩阵
```

不改变其他五个Tab。

**Step 3: 更新指标字典文档**

记录：

- 每个派生指标的公式；
- 权重时点；
- 最小历史窗口；
- CR3不可解释区间与>100%含义；
- HHI只使用正贡献；
- 方差与标准差的单位；
- 状态分类规则；
- 数据来源均为真实季度行业不变价GDP。

**Step 4: 运行渲染测试**

Run:

```powershell
python -m pytest tests/analysis/uae/test_renderer.py -p no:cacheprovider --basetemp C:\tmp\htfa_industry_renderer -q
```

Expected: 全部通过。

---

### Task 7: 完整验证

**Files:** No production changes expected.

**Step 1: 运行完整UAE测试**

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/analysis/uae -p no:cacheprovider --basetemp C:\tmp\htfa_industry_quality_full -q
```

Expected: 现有53项及新增测试全部通过。

**Step 2: 运行静态检查**

```powershell
python -m ruff check dashboard/analysis/uae tests/analysis/uae
python -m compileall -q app.py dashboard tests
git diff --check
```

Expected:

- Ruff无新增问题；
- compileall退出码0；
- diff-check退出码0；CRLF提示可记录但不视为失败。

**Step 3: 真实工作簿烟雾检查**

对 `data/阿联酋.xlsx` 生成结果并记录：

- 16个行业；
- 52个同比季度；
- 每季度权重和为1；
- 三个新图均可构造；
- 最新状态覆盖全部16行业；
- CR3非正增长季度显示断点；
- 行业分析Tab总计6张图，无Streamlit异常。

**Step 4: 工作区保护**

当前工作区已有与UAE监测直接相关的未提交改动。不得重置、覆盖或提交用户改动；除非用户另行明确要求，不执行 `git add`、`git commit` 或清理操作。

## 4. 完成标准

只有同时满足以下条件才可报告完成：

1. 四类广度条件均同时提供不加权与上年同期权重加权结果。
2. 广度历史均值无前视，缺失行业不缩小分母。
3. CR3在非油增长非正时为缺失，超过100%时不截断。
4. HHI只基于正贡献；无正贡献时为缺失。
5. 离散度原始加权方差和可解释的加权标准差均可复核。
6. 五项行业持续性统计与四状态分类均有合成测试。
7. 新功能只依赖现有实际GDP行业数据。
8. 现有行业拉动图和量价四象限图回归不变。
9. 完整UAE测试、Ruff、compileall和diff-check通过。

