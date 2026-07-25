# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

HTFA（经济运行分析平台）是一个基于 Streamlit 的数据分析仪表板应用，用于经济数据的监测、分析和预测。

**技术栈**: Python 3.11 + Streamlit + Pandas + Plotly/Altair + statsmodels
**架构**: 模块化单体应用，垂直切分架构
**部署**: Docker 容器化，端口 8501

## 常用命令

```bash
# 启动应用（开发模式）
streamlit run app.py --server.port=8501

# 直接运行（会自动清理缓存和端口）
python app.py

# Docker 部署
docker-compose up -d

# 安装依赖
pip install -r requirements.txt
```

## 核心架构

### 目录结构

```
HTFA/
├── app.py                    # 应用入口，页面配置和主路由
├── dashboard/                # Dashboard 模块
│   ├── core/                 # 核心框架
│   │   ├── backend/          # 后端服务
│   │   │   ├── config/       # 配置管理
│   │   │   ├── navigation/   # 导航状态管理
│   │   │   ├── resource/     # 资源加载器
│   │   │   └── initialization/   # 初始化器
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
│   │   ├── ui/               # 单变量/双变量分析页面
│   │   └── metrics/          # 相关性计算
│   └── preview/              # 数据预览模块
│       ├── core/             # 基础加载器和渲染器
│       └── modules/          # 各领域预览模块
├── data/                     # 数据文件
├── logs/                     # 日志文件
└── config/                   # 配置文件
```

### 模块配置（app.py:230-245）

```python
MODULE_CONFIG = {
    "数据预览": {"工业": None},
    "监测分析": {"工业": ["工业增加值", "工业企业利润"]},
    "模型分析": {"DFM 模型": ["数据准备", "模型训练", "模型分析", "新闻分析"]},
    "数据探索": {"时序性质": ["平稳性检验"], "时序关系": ["相关分析", "领先滞后分析"]},
    "用户管理": None
}
```

### 关键设计模式

1. **导航状态管理**: 通过 `dashboard.core.backend.navigation` 管理主模块/子模块状态
   - `get_current_main_module()` / `set_current_main_module()`
   - `get_current_sub_module()` / `set_current_sub_module()`
   - `is_transitioning()` / `set_transitioning()` 控制页面切换状态

2. **内容路由**: `dashboard/core/ui/components/content_router.py` 根据导航状态路由到对应模块

3. **权限控制**:
   - 调试模式（`HTFA_DEBUG_MODE=true`）跳过认证
   - 生产模式通过 `AuthManager` 和 `PermissionManager` 控制模块访问

4. **UI 组件基类**: `dashboard.core.ui.components.base.UIComponent`

## 环境变量

```bash
HTFA_DEBUG_MODE=true      # 调试模式，跳过认证
PYTHONPATH=/app           # Docker 环境
STREAMLIT_SERVER_PORT=8501
```

## 数据目录

- `data/` - 数据文件（Excel、CSV）
- `logs/` - 日志文件
- `config/` - 配置文件

## 注意事项

- 使用 `st.session_state` 管理所有状态
- 样式通过 `inject_cached_styles()` 注入
- 图表使用 Altair（启用 vegafusion 转换器）和 Plotly
- 认证数据存储在 SQLite 数据库
