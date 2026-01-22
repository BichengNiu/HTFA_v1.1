# -*- coding: utf-8 -*-
"""
统一UI组件库
提供标准化的UI组件和页面模板，包含静态资源管理
"""

__version__ = "1.0.0"
__author__ = "HFTA Development Team"

# 导入核心组件
from dashboard.core.ui.components.welcome import WelcomeComponent
from dashboard.core.ui.components.layout import LayoutComponent
from dashboard.core.ui.components.cards import ModuleCard, FeatureCard
from dashboard.core.ui.utils.tab_detector import TabStateDetector
from dashboard.core.ui.constants import UIConstants, NavigationLevel

# 导入迁移的样式功能
from dashboard.core.ui.utils.style_loader import (
    StyleLoader,
    inject_cached_styles,
    load_cached_styles,
    get_style_loader
)

# 导入UI初始化功能
from dashboard.core.ui.utils.style_initializer import (
    UIInitializer,
    initialize_ui,
    load_ui_styles,
    is_ui_initialized,
    get_ui_initializer
)

# 导入组件注册功能
from dashboard.core.ui.components.registry import (
    ComponentRegistry,
    get_component_registry,
    register_ui_component,
    get_ui_component_path,
    get_ui_component_dependencies
)

# 导入新的UI组件
from dashboard.core.ui.components.data_input import (
    DataInputComponent,
    UnifiedDataUploadComponent,
    DataUploadSidebar,
    DataValidationComponent,
    DataStagingComponent,
)

# 静态资源路径
import os
from pathlib import Path
STATIC_DIR = Path(__file__).parent / "static"

__all__ = [
    'WelcomeComponent',
    'LayoutComponent',
    'ModuleCard',
    'FeatureCard',
    'TabStateDetector',
    'UIConstants',
    'NavigationLevel',
    'STATIC_DIR',
    # 样式功能
    'StyleLoader',
    'inject_cached_styles',
    'load_cached_styles',
    'get_style_loader',
    # UI初始化功能
    'UIInitializer',
    'initialize_ui',
    'load_ui_styles',
    'is_ui_initialized',
    'get_ui_initializer',
    # 组件注册功能
    'ComponentRegistry',
    'get_component_registry',
    'register_ui_component',
    'get_ui_component_path',
    'get_ui_component_dependencies',
    # 数据输入组件
    'DataInputComponent',
    'UnifiedDataUploadComponent',
    'DataUploadSidebar',
    'DataValidationComponent',
    'DataStagingComponent',
]
