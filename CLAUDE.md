# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

HTFA（经济运行分析平台）是一个基于 Streamlit 的数据分析仪表板应用，用于经济数据的监测、分析和预测。

**技术栈**: Python 3.13.4 + Streamlit + Pandas + Plotly/Altair + statsmodels
**架构**: 模块化单体应用，垂直切分架构
**部署**: Docker 容器化，端口 8501

## 常用命令

```powershell
# 首次创建或安全重建唯一运行时
scripts\windows\setup_runtime.bat

# 启动应用
runtime\python.exe scripts\run_htfa.py --server.port=8501

# 完整测试与依赖检查
runtime\python.exe -m pytest -q -c tooling\pytest.ini
runtime\python.exe -m pip check

# Docker 部署
docker compose -f tooling\docker\docker-compose.yml up --build -d
```

## 核心架构

### 目录结构

```
HTFA/
├── app.py                    # 应用入口，页面配置和主路由
├── tooling/                  # 依赖、pytest 与 Docker 配置
├── scripts/                  # 维护脚本和 Windows 入口
│   └── data_sources/         # 纳入版本控制的数据获取与转换代码
├── dashboard/                # Dashboard 模块
│   ├── core/                 # 核心框架
│   │   ├── backend/          # 后端服务
│   │   │   ├── navigation/   # 导航状态管理
│   │   │   └── utils/        # 后端通用工具
│   │   └── ui/               # UI 框架
│   │       ├── components/   # 通用组件（sidebar, content_router, layout）
│   │       └── utils/        # UI 工具（样式加载、状态管理、调试）
│   ├── auth/                 # 认证模块
│   │   ├── authentication.py # AuthManager 认证管理器
│   │   ├── models.py         # User, UserSession 数据模型
│   │   ├── database.py       # SQLite 数据库操作
│   │   ├── security.py       # 密码哈希、输入验证
│   │   └── ui/               # 登录界面、用户管理界面
│   ├── analysis/             # 监测分析模块
│   │   └── industrial/       # 工业分析（图表、计算、UI）
│   ├── models/               # 模型分析模块
│   │   └── DFM/              # 动态因子模型
│   │       ├── prep/         # 数据准备
│   │       ├── train/        # 模型训练
│   │       ├── results/      # 结果分析
│   │       └── decomp/       # 影响分解
│   ├── explore/              # 数据探索模块
│   │   ├── analysis/         # 统计分析规则
│   │   ├── preprocessing/    # 频率对齐与标准化
│   │   ├── metrics/          # 距离、相关性等指标
│   │   └── ui/               # 单变量/双变量分析页面
│   └── preview/              # 数据预览模块
│       ├── core/             # 基础加载器和渲染器
│       └── modules/          # 各领域预览模块
├── data/                     # 仅保存在本地的数据；Git 只跟踪 README
├── references-local/         # 仅保存在本地的二进制参考资料
├── logs/                     # 运行日志文件
└── config/                   # 运行时配置文件
```

### 模块配置（dashboard/navigation_config.py）

```python
MODULE_CONFIG = ...  # 由 GRANULAR_PERMISSION_MAP 派生，禁止维护第二份导航树
```

### 关键设计模式

1. **导航状态管理**: 通过 `dashboard.core.backend.navigation` 管理主模块/子模块状态
   - `get_current_main_module()` / `set_current_main_module()`
   - `get_current_sub_module()` / `set_current_sub_module()`
2. **内容路由**: `dashboard/core/ui/components/content_router.py` 根据导航层级直接分派页面；渲染函数不返回状态协议

3. **权限控制**:
   - 调试模式（`HTFA_DEBUG_MODE=true`）跳过认证
   - 生产模式通过 `AuthManager` 和 `PermissionManager` 控制模块访问

4. **状态隔离**: 跨页面状态使用 `NamespacedStateManager` 或领域内状态管理器，键名保持模块命名空间

5. **DFM 数据流**: 上传工作簿和训练 DataFrame 在内存中传递；不得为 UI/训练桥接创建长期临时 Excel/CSV 文件

## 环境变量

```bash
HTFA_DEBUG_MODE=true      # 调试模式，跳过认证
PYTHONPATH=/app           # Docker 环境
STREAMLIT_SERVER_PORT=8501
```

## 数据目录

- `data/` - 本地数据文件（Excel、CSV、PDF、数据库），不推送 GitHub
- `references-local/` - 本地论文、报告和办公文档，不推送 GitHub
- `scripts/data_sources/` - 可复现的数据获取与转换代码，纳入版本控制
- `logs/` - 日志文件
- `config/` - 配置文件

## 注意事项

- 使用 `st.session_state` 管理所有状态
- 样式通过 `inject_cached_styles()` 注入
- 图表使用 Altair（启用 vegafusion 转换器）和 Plotly
- 认证数据存储在 SQLite 数据库
