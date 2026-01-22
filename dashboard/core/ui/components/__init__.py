# -*- coding: utf-8 -*-
"""
UI基础组件模块
"""

# 延迟导入避免循环导入
from dashboard.core.ui.components.base import UIComponent
from dashboard.core.ui.components.welcome import WelcomeComponent
from dashboard.core.ui.components.layout import LayoutComponent
from dashboard.core.ui.components.cards import ModuleCard, FeatureCard

# 导入数据输入组件
from dashboard.core.ui.components.data_input import (
    DataInputComponent,
    UnifiedDataUploadComponent,
    DataUploadSidebar,
    DataValidationComponent,
    DataStagingComponent,
)

# 导入组件注册功能
from dashboard.core.ui.components.registry import (
    ComponentRegistry,
    get_component_registry,
    register_ui_component,
    get_ui_component_path,
    get_ui_component_dependencies
)

__all__ = [
    'UIComponent',
    'WelcomeComponent',
    'LayoutComponent',
    'ModuleCard',
    'FeatureCard',
    # 组件注册功能
    'ComponentRegistry',
    'get_component_registry',
    'register_ui_component',
    'get_ui_component_path',
    'get_ui_component_dependencies',
]

__all__.extend([
    # 数据输入组件
    'DataInputComponent',
    'UnifiedDataUploadComponent',
    'DataUploadSidebar',
    'DataValidationComponent',
    'DataStagingComponent',
])
