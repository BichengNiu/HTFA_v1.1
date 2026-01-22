# -*- coding: utf-8 -*-
"""
Core基础框架模块
提供应用基础服务和UI框架，遵循垂直切分架构

架构说明：
- backend/: 后端基础服务（配置、导航、资源加载、初始化等）
- ui/: 前端UI框架（组件、工具、样式等）
"""

# ========== 后端服务导出 ==========

# 配置管理
from dashboard.core.backend.config import (
    get_core_config
)

# 导航管理 - 只导出辅助函数，不导出不存在的 get_navigation_manager
from dashboard.core.backend.navigation import (
    NavigationStateKeys,
    get_current_main_module,
    get_current_sub_module,
    set_current_main_module,
    set_current_sub_module,
    is_transitioning,
    set_transitioning,
    reset_navigation
)

# 资源加载
from dashboard.core.backend.resource import (
    get_resource_loader
)

# ========== UI框架导出 ==========
# 注意：UI组件应该由各业务模块直接导入，core 不应该重导出所有 UI 组件
# 这里只导出核心基类和最常用的工具

# UI基类
from dashboard.core.ui.components.base import UIComponent

# UI工具 - 只导出最常用的
from dashboard.core.ui.utils.style_loader import inject_cached_styles
from dashboard.core.ui.utils.state_helpers import get_state, set_state

__version__ = "5.0.0"

__all__ = [
    # ===== Backend Services =====
    'get_core_config',

    # Navigation
    'NavigationStateKeys',
    'get_current_main_module',
    'get_current_sub_module',
    'set_current_main_module',
    'set_current_sub_module',
    'is_transitioning',
    'set_transitioning',
    'reset_navigation',

    # Resource Loading
    'get_resource_loader',

    # ===== UI Framework =====
    'UIComponent',
    'inject_cached_styles',
    'get_state',
    'set_state'
]
