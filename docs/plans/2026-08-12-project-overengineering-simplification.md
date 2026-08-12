# Project Overengineering Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 删除审计确认的无效抽象、重复配置和临时文件管线，同时保持页面行为、统计语义、权限边界与运行时安全不变。

**Architecture:** 以真实调用链为边界做减法：路由函数直接分派页面，状态通过现有 `NamespacedStateManager` 统一访问，Preview 只保留一份类型化频率配置，DFM 在内存中传递上传内容与训练数据。保留 UAE 证据契约、Preview 延迟注册表、Explore 分析状态签名、DFM 分解边界和 Ts 运行时安全设施。

**Tech Stack:** Python 3.13、Streamlit、pandas、pytest、项目本地 `runtime\\python.exe`

---

### Task 1: Core 路由与状态 API

**Files:**
- Modify: `app.py`
- Modify: `dashboard/core/ui/components/content_router.py`
- Modify: `dashboard/core/ui/utils/state_helpers.py`
- Test: `tests/core/`

1. 将 `render_main_content` 改为直接分派且不返回未使用的状态字典。
2. 保留导航识别、权限拒绝、错误显示和 DFM 子标签过滤行为。
3. 删除没有运行时调用者的状态枚举与便捷函数，收紧导出面。
4. 运行 core、app 与 auth 定向测试。

### Task 2: Auth、Industrial、Preview 与 Explore

**Files:**
- Modify: `dashboard/auth/`
- Modify: `dashboard/analysis/industrial/`
- Modify: `dashboard/preview/shared/`
- Modify: `dashboard/explore/`
- Test: `tests/auth/`, `tests/analysis/`, `tests/preview/`, `tests/explore/`

1. 令登录和注册页面显式接收依赖，移除惰性回退构造造成的循环导入。
2. 将工业分析状态包装类替换为单个命名空间状态对象，删除未调用的加权管线和页面函数，并改用直接模块导入。
3. 合并 Preview 的频率配置表示，删除无调用辅助函数；保留延迟注册表及领域适配层。
4. 移除 Explore 顶层兼容门面，将基类缩减为实际共享的状态和错误处理能力。
5. 分模块运行回归测试。

### Task 3: DFM 数据流与包装层

**Files:**
- Modify: `dashboard/models/DFM/prep/`
- Modify: `dashboard/models/DFM/train/`
- Modify: `dashboard/models/DFM/results/`
- Modify: `dashboard/models/DFM/decomp/`
- Test: `tests/test_dfm_boundaries.py`
- Test: `tests/models/DFM/`

1. 以上传内容指纹缓存 Prep 解析，移除长期存活的临时 Excel 文件集合。
2. 让训练配置和训练器直接接收 DataFrame，去掉 UI 写临时 CSV 后再读回的路径。
3. 合并串行/并行评估配置构建逻辑。
4. 删除无调用的 DFM UI/date/value-replacement API、纯转发状态闭包和静态指标类。
5. 增加数据流与架构边界回归测试。

### Task 4: 文档与全量验证

**Files:**
- Modify: `CLAUDE.md`
- Modify: affected tests

1. 修正文档中的已删除目录、状态 API 和 UI 基类说明。
2. 运行 DFM 与非 DFM 两组完整 pytest，避免单次超时掩盖结果。
3. 运行 `compileall`、`pip check`、`git diff --check`。
4. 精确清理验证产生的缓存，确认没有用户文件或运行时数据被删除。
5. 汇总行为保持证据、测试结果和剩余风险；不提交、不推送。
