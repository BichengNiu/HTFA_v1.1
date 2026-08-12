# HTFA 过度工程清理 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 删除已审计确认的无效抽象、重复状态和历史平行模块，同时保持现有 Streamlit 页面、权限、统计计算和数据失效语义不变。

**Architecture:** 以真实入口 `app.py` 为起点沿调用链收缩实现。导航只保留主模块与子模块两个会话状态；认证组件共享一个数据库适配器；UAE 石油功能成为 `dashboard.analysis.uae.oil` 子包；DFM 和 Explore 直接使用最小状态及错误处理函数，不保留单实现基类。

**Tech Stack:** Python 3.13、Streamlit、pandas、pytest、项目本地 `runtime\\python.exe`

---

### Task 1: 简化 Core 导航状态

**Files:**
- Modify: `dashboard/core/backend/navigation/manager.py`
- Modify: `dashboard/core/backend/navigation/__init__.py`
- Modify: `dashboard/core/__init__.py`
- Modify: `dashboard/core/ui/components/module_selector.py`
- Modify: `dashboard/core/ui/components/sidebar/renderer.py`
- Modify: `tests/test_core_boundaries.py`

**Steps:**

1. 在 `tests/test_core_boundaries.py` 增加断言：导航模块只公开主/子模块读写与重置接口，不再公开 previous、transitioning、timestamp 或导航缓存接口。
2. 运行 `runtime\\python.exe -m pytest tests\\test_core_boundaries.py -q`，预期新增断言先失败。
3. 将导航键缩减为 `navigation.main_module` 和 `navigation.sub_module`；主模块改变时直接清空子模块。
4. 让模块选择器直接返回选中字符串，删除 `success/has_change` 结果字典、过渡标志和写后自检。
5. 让侧边栏仅负责权限过滤、选择与共享上传器渲染，不构造无人消费的汇总结果。
6. 重新运行该测试，预期通过。

### Task 2: 共享 Auth 数据库依赖

**Files:**
- Modify: `dashboard/auth/authentication.py`
- Modify: `dashboard/auth/permissions.py`
- Modify: `dashboard/auth/ui/middleware.py`
- Modify: `dashboard/auth/ui/pages/login.py`
- Modify: `dashboard/auth/ui/pages/register.py`
- Modify: `dashboard/auth/ui/pages/user_management.py`
- Create: `tests/auth/test_dependency_wiring.py`

**Steps:**

1. 写测试构造一个临时 `AuthDatabase`，断言 middleware、认证管理器和需要持久化的页面使用同一对象，同时权限管理器不再持有数据库。
2. 运行 `runtime\\python.exe -m pytest tests\\auth\\test_dependency_wiring.py -q`，预期先失败。
3. 为 `AuthManager` 和页面构造器增加可选数据库对象注入；middleware 创建一次数据库并向下传递。
4. 删除 `PermissionManager` 中未使用的数据库成员；如果页面只需权限纯函数，则只注入权限管理器。
5. 运行认证依赖测试，预期通过。

### Task 3: 将 UAE 石油模块并入主包

**Files:**
- Create: `dashboard/analysis/uae/oil/__init__.py`
- Move: `dashboard/analysis/uae_v2/oil_charts.py` to `dashboard/analysis/uae/oil/charts.py`
- Move: `dashboard/analysis/uae_v2/oil_data.py` to `dashboard/analysis/uae/oil/data.py`
- Move: `dashboard/analysis/uae_v2/oil_revenue.py` to `dashboard/analysis/uae/oil/revenue.py`
- Move: `dashboard/analysis/uae_v2/renderer.py` to `dashboard/analysis/uae/oil/renderer.py`
- Modify: `dashboard/analysis/uae/renderer.py`
- Delete: `dashboard/analysis/uae_v2/__init__.py`
- Move: `tests/analysis/uae_v2/test_oil_market.py` to `tests/analysis/uae/test_oil_market.py`
- Modify: `tests/analysis/uae/test_runtime_boundaries.py`

**Steps:**

1. 更新测试导入到 `dashboard.analysis.uae.oil`，并断言仓库不再存在 `uae_v2` 运行包。
2. 运行 UAE 测试，预期新导入先失败。
3. 移动代码并改为包内相对导入；主 UAE renderer 直接导入正式 oil renderer。
4. 确认已删除的模拟面板没有恢复；不可用主题继续由真实指标缺失说明驱动。
5. 运行 `runtime\\python.exe -m pytest tests\\analysis\\uae -q`，预期通过。

### Task 4: 删除 DFM 空壳基类和单方法服务类

**Files:**
- Create: `dashboard/models/DFM/ui/state.py`
- Modify: `dashboard/models/DFM/ui/__init__.py`
- Delete: `dashboard/models/DFM/ui/base.py`
- Modify: `dashboard/models/DFM/results/ui/pages/model_analysis_page.py`
- Modify: `dashboard/models/DFM/decomp/ui/pages/news_analysis_page.py`
- Modify: `dashboard/models/DFM/train/utils/__init__.py`
- Delete: `dashboard/models/DFM/train/utils/state_manager.py`
- Modify: `dashboard/models/DFM/train/ui/pages/model_training_page.py`
- Modify: `dashboard/models/DFM/prep/services/ui_backend_service.py`
- Modify: `dashboard/models/DFM/prep/ui/pages/data_prep_page.py`
- Modify: `dashboard/models/DFM/prep/ui/__init__.py`
- Delete: `dashboard/models/DFM/prep/ui/state_keys.py`
- Modify: `dashboard/models/DFM/prep/config.py`
- Modify: `dashboard/models/DFM/decomp/utils/__init__.py`
- Delete: `dashboard/models/DFM/decomp/utils/logging_config.py`
- Modify: `tests/test_dfm_boundaries.py`

**Steps:**

1. 添加边界测试，禁止 `DFMComponent`、旧 `DataPrepStateKeys`、`UIBackendService` 类、空壳 `StateManager` 子类和独立日志工厂重新出现。
2. 运行 `runtime\\python.exe -m pytest tests\\test_dfm_boundaries.py -q`，预期先失败。
3. 将实际使用的 DFM 状态闭包移到 `ui/state.py`；训练页面直接使用 `NamespacedStateManager`。
4. 将变量转换服务改为模块级 `transform_variables` 函数，并更新唯一调用点。
5. 删除未使用的训练配置对象、旧状态键和日志包装文件；并行配置只保留现有频率处理真正读取的字段。
6. 重新运行边界测试，预期通过。

### Task 5: 收缩 Explore 与通用 UI 抽象

**Files:**
- Modify: `dashboard/core/ui/utils/error_handler.py`
- Delete: `dashboard/core/ui/components/base.py`
- Modify: `dashboard/explore/ui/base.py`
- Modify: `dashboard/explore/ui/pages.py`
- Modify: `dashboard/explore/ui/__init__.py`
- Delete: `dashboard/explore/ui/unified_correlation.py`
- Modify: `dashboard/explore/ui/bivariate_page.py`
- Modify: `dashboard/explore/analysis/lead_lag.py`
- Modify: `dashboard/core/ui/components/content_router.py`
- Create: `tests/explore/test_architecture_boundaries.py`

**Steps:**

1. 写边界测试，断言 Explore 不再依赖通用 `UIComponent`，欢迎页使用函数入口，同步分析包装文件和未调用的 `get_overlapping_series` 已移除。
2. 运行 `runtime\\python.exe -m pytest tests\\explore\\test_architecture_boundaries.py -q`，预期先失败。
3. 在时间序列基类中直接实现其真实需要的命名空间状态和错误记录；将错误处理器单例类收缩为一个返回结构化信息的函数。
4. 将无状态欢迎页改为渲染函数；将仅包装 DTW 的同步分析直接内联到多变量页面。
5. 保留 `exploration.bivariate.data_signature` 和 `_clear_bivariate_results()`，确保切换文件/表后旧结果仍失效。
6. 重新运行 Explore 边界和现有 Streamlit 测试，预期通过。

### Task 6: 全项目验证与残留审计

**Files:**
- Verify: `app.py`
- Verify: `dashboard/preview/**`
- Verify: `dashboard/analysis/industrial/**`
- Verify: `dashboard/**`
- Verify: `tests/**`

**Steps:**

1. 运行针对性测试：`runtime\\python.exe -m pytest tests\\test_core_boundaries.py tests\\auth tests\\analysis\\test_industrial_boundaries.py tests\\analysis\\uae tests\\test_dfm_boundaries.py tests\\explore -q`，预期全部通过。
2. 运行 `runtime\\python.exe -m compileall app.py dashboard scripts`，预期无语法或导入布局错误。
3. 运行 `runtime\\python.exe -m pytest -q`，预期全量通过且无新增 warning/error。
4. 用 `rg` 搜索已删除名称和 `uae_v2`，预期运行代码与测试中无残留引用；历史计划文档可以保留原始记录。
5. 删除本轮验证产生的精确缓存目录，再运行 `git status --short`；只应看到本计划内源码、测试和计划文件改动。

---

## Execution Result

- Core、Auth、Industrial、UAE、DFM、Explore、Preview 与运行脚本均完成调用链复核。
- `runtime\\python.exe -m compileall app.py dashboard scripts`：通过。
- `runtime\\python.exe -m pytest -q`：227 passed。
- 运行代码中的旧类名、`uae_v2` 导入和已删除并行开关：无残留。
