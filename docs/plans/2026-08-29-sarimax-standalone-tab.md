# SARIMAX 独立标签页 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为动态回归模型增加浏览器独立标签页入口，复制当前 SARIMAX 自有数据、读取设置、可编辑模型输入以及当前拟合、诊断和预测结果。

**Architecture:** 复用数据探索已有的短期不透明交接令牌模式，并抽取通用进程内 `HandoffStore`。SARIMAX 独立页恢复文件资产、控件快照和深拷贝的结果缓存后，调用同一套动态回归模型页面渲染器；独立 Streamlit 会话使用相同的页面命名空间，但不共享来源会话状态。内置数据源增加“已恢复文件”边界，使交接文件可以在没有原上传器 widget 状态的情况下继续参与解析。

**Tech Stack:** Python 3.13, Streamlit, pandas, pytest, Streamlit `AppTest`, 现有 `SessionWorkspace` 与 `data_overview` 组件。

---

### Task 1: 记录领域边界和通用交接存储

**Files:**
- Modify: `CONTEXT.md`
- Create: `docs/adr/0002-sarimax-standalone-page-handoff.md`
- Create: `dashboard/core/workspace/handoff.py`
- Modify: `dashboard/explore/core/overview_handoff.py`
- Test: `tests/explore/test_overview_handoff.py`

**Step 1:** 保留现有数据概览交接 API，并让其使用通用、带 TTL 的不透明令牌存储。

**Step 2:** 为 SARIMAX 提供同一存储能力，保证令牌不包含文件内容、读取设置或模型结果本身；结果快照保存在令牌对应的进程内存储中，过期和替换行为与数据概览一致。

**Step 3:** 运行交接存储回归测试，确认旧数据概览行为不变。

Run: `runtime\\python.exe -m pytest -c tooling\\pytest.ini tests\\explore\\test_overview_handoff.py -q`

Expected: 全部现有交接测试通过。

### Task 2: 支持恢复 SARIMAX 自有文件、输入和结果状态

**Files:**
- Modify: `components/data_overview/ui/data_source.py`
- Modify: `dashboard/models/SARIMAX/ui/data_input.py`
- Create: `dashboard/models/SARIMAX/ui/standalone_model.py`

**Step 1:** 为内置数据源增加已恢复文件的最小恢复边界，保留原有真实上传文件路径和读取错误处理。

**Step 2:** 导出当前 SARIMAX `FileAsset`、工作表和非按钮/下载控件状态；恢复时跳过“新数据集清理”回调的一次性清理，并预置读取设置签名。

**Step 3:** 深拷贝并导出 `fitted_result`、拟合签名、诊断表、诊断签名、预测对象、预测签名及预测窗口关联签名；恢复后两页的结果对象可以分别继续使用，未来外生变量来源和可编辑表格仍作为输入状态恢复。

### Task 3: 接入独立页面路由和来源页入口

**Files:**
- Modify: `dashboard/models/SARIMAX/ui/pages/sarimax_page.py`
- Modify: `app.py`
- Modify: `dashboard/models/SARIMAX/ui/pages/__init__.py`

**Step 1:** 在动态回归模型数据读取区下方显示“复制到独立标签页”入口，未上传有效文件时显示提示。

**Step 2:** 在应用入口识别 `view=sarimax-model`，恢复交接快照后渲染同一动态回归模型工作流，不渲染主系统侧边栏。

**Step 3:** 保持来源页和独立页分别修改文件、配置和结果；独立页打开后直接显示已复制的结果，不需要自动重新拟合。

### Task 4: 增加回归测试

**Files:**
- Create or Modify: `tests/models/test_sarimax_standalone.py`
- Modify: `tests/models/test_sarimax_ui_flow.py` when shared helpers are useful

**Step 1:** 测试 URL 不泄漏文件名、文件内容或模型结果，并在重复重跑时复用未变化令牌。

**Step 2:** 用 `AppTest` 上传 SARIMAX 文件、修改读取/模型输入、完成拟合/诊断/预测后打开独立页，验证独立页恢复三类结果且来源页修改不影响独立页。

**Step 3:** 验证非法/过期令牌只显示交接错误，不渲染主系统导航。

### Task 5: 完整验证

Run:

```powershell
runtime\\python.exe -m pytest -c tooling\\pytest.ini tests\\models\\test_sarimax_standalone.py tests\\models\\test_sarimax_ui_flow.py tests\\models\\test_sarimax_boundaries.py -q
runtime\\python.exe -m pytest -c tooling\\pytest.ini tests\\explore\\test_standalone_data_overview.py tests\\explore\\test_overview_handoff.py -q
runtime\\python.exe -m compileall -q app.py dashboard components
git diff --check
```

Expected: 相关测试全部通过，无编译错误、空白错误或未授权文件改动；最后复核 `git status --short`，只保留本功能及原有用户改动。
