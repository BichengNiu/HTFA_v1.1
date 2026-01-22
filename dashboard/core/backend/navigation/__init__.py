# -*- coding: utf-8 -*-
"""
导航管理模块
提供导航状态管理的核心函数
"""

from dashboard.core.backend.navigation.manager import (
    NavigationStateKeys,
    get_navigation_state,
    set_navigation_state,
    get_current_main_module,
    get_current_sub_module,
    set_current_main_module,
    set_current_sub_module,
    is_transitioning,
    set_transitioning,
    get_last_navigation_time,
    reset_navigation,
    clear_navigation_cache,
    get_navigation_state_info
)

__all__ = [
    'NavigationStateKeys',
    'get_navigation_state',
    'set_navigation_state',
    'get_current_main_module',
    'get_current_sub_module',
    'set_current_main_module',
    'set_current_sub_module',
    'is_transitioning',
    'set_transitioning',
    'get_last_navigation_time',
    'reset_navigation',
    'clear_navigation_cache',
    'get_navigation_state_info'
]
