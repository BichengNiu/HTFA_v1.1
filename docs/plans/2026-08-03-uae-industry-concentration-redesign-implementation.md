# UAE Industry Concentration Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将行业增长集中度三联图合并为一张方向—集中度气泡图，并增加Plotly图内季度时间轴和完整指标解读。

**Architecture:** 在 `calculate_industry_diagnostics` 中从既有行业增长贡献表派生贡献平衡指数、绝对贡献HHI、固定16行业标准化集中度、总变动强度和最大正负驱动，保持计算与UI分离。Plotly使用一张二维气泡图和季度frames；图内slider切换截至当前季度的历史轨迹，当前季度单独高亮，所有frame共用完整样本确定的坐标与气泡尺度。

**Tech Stack:** Python 3.11、pandas、NumPy、Plotly、Streamlit、pytest

---

### Task 1: 用失败测试固定新指标合同

**Files:**
- Modify: `tests/analysis/uae/test_growth.py`
- Modify: `tests/analysis/uae/test_services.py`

**Steps:**

1. 对贡献 `[6, 4, 2, -4]` 断言平衡指数50、绝对贡献HHI、标准化集中度、总变动强度16及最大正负驱动。
2. 对贡献 `[2, 1, -3, -5]` 断言平衡指数为 `-5/11×100`，验证净收缩与集中度相互独立。
3. 对全部负贡献断言平衡指数－100且绝对贡献HHI仍然有效。
4. 对全部行业无变动断言整行集中度指标为空。
5. 服务集成测试独立复核当前工作簿最新季度的新指标和驱动行业。
6. 先运行专项测试并确认旧实现失败，再进入实现。

### Task 2: 实现方向—集中度地图指标

**Files:**
- Modify: `dashboard/analysis/uae/growth.py`

**Steps:**

1. 计算总变动强度 `Σ|cᵢ|` 和贡献平衡指数 `Σcᵢ/Σ|cᵢ|×100`。
2. 计算绝对贡献HHI和固定16行业标准化集中度。
3. 派生最大正向、最大负向贡献行业及其百分点值。
4. 行业贡献缺失或总变动强度为0时整组指标为空。
5. 删除旧正向HHI、正向行业数、加权标准差和负向拖累占比合同。

### Task 3: 重构为单张气泡图并增加时间滑块

**Files:**
- Modify: `dashboard/analysis/uae/charts.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Steps:**

1. 横轴固定－100到100；纵轴按完整样本最大值留出20%余量并固定，最低上限20、最高100；横轴0线作为方向分界。
2. 气泡面积使用总变动强度；净增长期为实心圆，净收缩期为空心圆。
3. 悬浮报告季度、非油GDP同比、两项坐标、绝对贡献HHI、总变动强度和最大正负驱动。
4. 使用Plotly `frames + layout.sliders + updatemenus`；每帧保留截至所选季度的历史点，当前季度以深色描边突出，并支持从头播放和暂停。
5. 图内标注纵轴实际显示范围与0—100理论范围；不设置任意集中/分散阈值。
6. 测试图形结构、固定轴、历史/当前分层、符号冗余编码、frame顺序、内置滑块及播放按钮。

### Task 4: 同步服务说明和指标字典

**Files:**
- Modify: `dashboard/analysis/uae/services.py`
- Modify: `docs/analysis/阿联酋经济监测变量字典.md`

**Steps:**

1. 删除旧三联图指标的公式和边界说明。
2. 增加贡献平衡、绝对贡献HHI、标准化集中度、总变动强度和最大驱动口径。
3. 说明图内时间轴不重新计算指标、纵轴完整样本固定聚焦规则及缺失/零变动空值边界。
4. 全局搜索确认运行时代码、测试和指标字典不再引用旧集中度字段。

### Task 5: 完整验证

**Files:**
- Verify only: `dashboard/analysis/uae/`
- Verify only: `tests/analysis/uae/`

**Steps:**

1. 运行 `python -m pytest tests/analysis/uae/test_growth.py tests/analysis/uae/test_services.py tests/analysis/uae/test_renderer.py -q`，预期全部通过。
2. 运行 `python -m pytest tests/analysis/uae -q`，预期全部通过。
3. 运行 `python -m compileall dashboard/analysis/uae tests/analysis/uae`，预期无语法错误。
4. 使用当前测试工作簿独立复核最新季度的平衡指数、标准化集中度、绝对贡献HHI、总变动强度和最大正负驱动。
5. 检查 `git diff --check` 和作用域内差异，不修改或提交无关文件。

### Task 6: 增加图下指标算法与解读

**Files:**
- Modify: `dashboard/analysis/uae/renderer.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Steps:**

1. 新增失败测试，断言说明expander标题为“指标算法与解读”、默认折叠，并包含横轴、纵轴、气泡面积、四种位置和空值边界。
2. 运行 `python -m pytest tests/analysis/uae/test_renderer.py -k explanation -q`，预期因说明函数尚未实现而失败。
3. 在renderer中集中定义简短Markdown说明，并通过独立函数渲染默认折叠expander。
4. 在“行业增长集中度”图的 `plotly_chart` 调用后立即渲染该expander，并保留已配置的其他行业图说明。
5. 运行渲染专项测试和 `python -m pytest tests/analysis/uae -q`，预期全部通过。
6. 运行Ruff、compileall和 `git diff --check`，预期全部通过。

### Task 7: 按分析叙事重排行业Tab

**Files:**
- Modify: `dashboard/analysis/uae/renderer.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Steps:**

1. 新增失败测试，固定六张图顺序为总量拉动、非油行业拉动、扩张广度、增长集中度、状态矩阵、量价四象限。
2. 新增失败测试，确认筛选后的series group严格遵循显式标题顺序，而不是原字典顺序。
3. 修改 `GROWTH_INDUSTRY_GROUPS` 顺序，并增加纯排序函数供 `_render_panel` 使用。
4. 在第一、第三和第五张图前分别渲染“长期趋势：总量与增长来源”“中长期结构：行业增长质量”“短期动能：行业状态与量价表现”三级标题。
5. 扩展Streamlit AppTest，断言三个小节标题按顺序各出现一次，行业Tab仍为六张图且无异常。
6. 运行 `python -m pytest tests/analysis/uae/test_renderer.py -q` 和 `python -m pytest tests/analysis/uae -q`，预期全部通过。
7. 运行Ruff、compileall和 `git diff --check`，预期全部通过；不提交无关工作区改动。

### Task 8: 简化行业增长广度图

**Files:**
- Modify: `dashboard/analysis/uae/charts.py`
- Modify: `dashboard/analysis/uae/renderer.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Steps:**

1. 将原八轨迹切换测试改为断言仅有两条不加权轨迹：“正增长行业比例”和“连续四季度正增长行业比例”。
2. 断言图表没有 `updatemenus`，两条轨迹的悬浮信息明确标注不加权口径，50%和80%参考线仍存在。
3. 精简 `build_industry_breadth_figure` 的必需字段和轨迹构造，删除权重切换按钮及隐藏加权轨迹。
4. 在renderer中将该图的可见标题改为“行业增长广度与持续性”，内部series group键暂不改变。
5. 运行 `python -m pytest tests/analysis/uae/test_renderer.py -k breadth -q`，预期通过。
6. 运行完整UAE测试、Ruff、compileall和 `git diff --check`，预期全部通过。

### Task 9: 为长期趋势和增长广度图增加指标说明

**Files:**
- Modify: `dashboard/analysis/uae/renderer.py`
- Modify: `tests/analysis/uae/test_renderer.py`

**Steps:**

1. 扩展说明渲染测试，覆盖GDP部门拉动、非油行业拉动、行业增长广度与持续性、行业增长集中度四个图表键，并确认其他图不渲染。
2. 测试每项说明包含专属公式或边界关键词，实际Streamlit行业Tab中的“指标算法与解读”expander数量从1增至4。
3. 在renderer中定义三项简明说明，并与现有集中度说明组成集中映射。
4. 将 `_render_series_group_explanation` 改为从映射取文案；未配置图表保持无操作。
5. 运行说明专项、完整renderer测试和完整UAE测试，预期全部通过。
6. 运行Ruff、compileall和 `git diff --check`，预期全部通过；不修改或提交无关工作区文件。
