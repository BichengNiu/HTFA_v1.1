# -*- coding: utf-8 -*-
"""
UI工具函数模块
"""

from dashboard.core.ui.utils.tab_detector import TabStateDetector
from dashboard.core.ui.utils.validators import UIValidator
from dashboard.core.ui.utils.style_loader import StyleLoader, inject_cached_styles, get_style_loader
from dashboard.core.ui.utils.style_initializer import initialize_ui, load_ui_styles, get_ui_initializer
from dashboard.core.ui.utils.state_helpers import StateNamespace, get_state, set_state, clear_state_by_prefix
from dashboard.core.ui.utils.error_handler import handle_error

__all__ = [
    'TabStateDetector',
    'UIValidator',
    # 样式功能
    'StyleLoader',
    'inject_cached_styles',
    'get_style_loader',
    # UI初始化功能
    'initialize_ui',
    'load_ui_styles',
    'get_ui_initializer',
    # 状态管理
    'StateNamespace',
    'get_state',
    'set_state',
    'clear_state_by_prefix',
    # 错误处理
    'handle_error'
]
