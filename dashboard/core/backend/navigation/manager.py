# -*- coding: utf-8 -*-
"""
导航管理器 - 简化版
提供导航状态管理的辅助函数，遵循KISS原则
"""

import time
import streamlit as st
from typing import Optional, Dict, Any


# ==================== 状态键常量 ====================

class NavigationStateKeys:
    """导航状态键常量"""
    MAIN_MODULE = 'main_module'
    SUB_MODULE = 'sub_module'
    PREVIOUS_MAIN = 'previous_main'
    PREVIOUS_SUB = 'previous_sub'
    TRANSITIONING = 'transitioning'
    LAST_NAVIGATION_TIME = 'last_navigation_time'

    @staticmethod
    def get_full_key(key: str) -> str:
        """获取完整的状态键（带命名空间）"""
        return f'navigation.{key}'


# ==================== 核心辅助函数 ====================

def get_navigation_state(key: str, default=None) -> Any:
    """
    获取导航状态

    Args:
        key: 状态键（不带navigation.前缀）
        default: 默认值

    Returns:
        状态值
    """
    full_key = NavigationStateKeys.get_full_key(key)
    return st.session_state.get(full_key, default)


def set_navigation_state(key: str, value: Any) -> None:
    """
    设置导航状态

    Args:
        key: 状态键（不带navigation.前缀）
        value: 状态值
    """
    full_key = NavigationStateKeys.get_full_key(key)
    st.session_state[full_key] = value


# ==================== 便捷函数 ====================

def get_current_main_module() -> Optional[str]:
    """获取当前主模块"""
    return get_navigation_state(NavigationStateKeys.MAIN_MODULE)


def get_current_sub_module() -> Optional[str]:
    """获取当前子模块"""
    return get_navigation_state(NavigationStateKeys.SUB_MODULE)


def set_current_main_module(module_name: Optional[str]) -> None:
    """设置当前主模块，同时清空子模块"""
    # 保存之前的主模块
    current_main = get_current_main_module()
    if current_main != module_name:
        set_navigation_state(NavigationStateKeys.PREVIOUS_MAIN, current_main)
        set_navigation_state(NavigationStateKeys.MAIN_MODULE, module_name)
        set_navigation_state(NavigationStateKeys.SUB_MODULE, None)
        set_navigation_state(NavigationStateKeys.LAST_NAVIGATION_TIME, time.time())
        clear_navigation_cache()


def set_current_sub_module(sub_module_name: Optional[str]) -> None:
    """设置当前子模块"""
    current_sub = get_current_sub_module()
    if current_sub != sub_module_name:
        set_navigation_state(NavigationStateKeys.PREVIOUS_SUB, current_sub)
        set_navigation_state(NavigationStateKeys.SUB_MODULE, sub_module_name)
        set_navigation_state(NavigationStateKeys.LAST_NAVIGATION_TIME, time.time())


def is_transitioning() -> bool:
    """检查是否正在转换"""
    return get_navigation_state(NavigationStateKeys.TRANSITIONING, False)


def set_transitioning(transitioning: bool) -> None:
    """设置转换状态"""
    set_navigation_state(NavigationStateKeys.TRANSITIONING, transitioning)


def get_last_navigation_time() -> float:
    """获取最后导航时间"""
    return get_navigation_state(NavigationStateKeys.LAST_NAVIGATION_TIME, 0)


def reset_navigation() -> None:
    """重置导航状态"""
    set_navigation_state(NavigationStateKeys.MAIN_MODULE, None)
    set_navigation_state(NavigationStateKeys.SUB_MODULE, None)
    set_navigation_state(NavigationStateKeys.PREVIOUS_MAIN, None)
    set_navigation_state(NavigationStateKeys.PREVIOUS_SUB, None)
    set_navigation_state(NavigationStateKeys.TRANSITIONING, False)


def clear_navigation_cache() -> None:
    """清除导航相关缓存"""
    from dashboard.core.backend.config import get_core_config

    config = get_core_config()
    cache_keys = config.get_cache_keys()
    for key in cache_keys:
        if key in st.session_state:
            del st.session_state[key]


def get_navigation_state_info() -> Dict[str, Any]:
    """获取当前导航状态信息"""
    return {
        'main_module': get_current_main_module(),
        'sub_module': get_current_sub_module(),
        'previous_main': get_navigation_state(NavigationStateKeys.PREVIOUS_MAIN),
        'previous_sub': get_navigation_state(NavigationStateKeys.PREVIOUS_SUB),
        'transitioning': is_transitioning(),
        'last_navigation_time': get_last_navigation_time()
    }


