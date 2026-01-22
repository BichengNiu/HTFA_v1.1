# -*- coding: utf-8 -*-
"""
状态管理辅助函数模块（简化版）
提供命名空间常量和基本辅助函数，直接使用st.session_state
"""

import streamlit as st
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


# === 命名空间定义 ===

class StateNamespace:
    """状态管理命名空间常量"""
    DASHBOARD = "dashboard"
    NAVIGATION = "navigation"
    DATA_INPUT = "data_input"
    ANALYSIS = "analysis"
    TOOLS = "tools"
    AUTH = "auth"
    CORE = "core"


# === 基础状态管理接口 ===

def get_state(namespace: str, key: str, default: Any = None) -> Any:
    """统一状态获取接口"""
    full_key = f"{namespace}.{key}"
    return st.session_state.get(full_key, default)


def set_state(namespace: str, key: str, value: Any) -> bool:
    """统一状态设置接口"""
    try:
        full_key = f"{namespace}.{key}"
        st.session_state[full_key] = value
        return True
    except Exception as e:
        logger.error(f"设置状态失败: {e}")
        return False


def clear_state_by_prefix(prefix: str) -> bool:
    """根据前缀清理状态"""
    try:
        keys_to_delete = [k for k in st.session_state.keys() if str(k).startswith(prefix)]
        for k in keys_to_delete:
            del st.session_state[k]
        logger.info(f"清理状态: 删除了{len(keys_to_delete)}个键（前缀: {prefix}）")
        return True
    except Exception as e:
        logger.error(f"清理状态失败: {e}")
        return False


# === 保留少量常用辅助函数以提供便利性 ===

def get_staged_data() -> dict:
    """获取暂存数据 - 常用操作，保留便利性"""
    return st.session_state.get("dashboard.staged_data", {})


def get_preview_state(key: str, default: Any = None) -> Any:
    """获取预览模块状态 - preview命名空间"""
    full_key = f"preview.{key}"
    return st.session_state.get(full_key, default)


def set_preview_state(key: str, value: Any) -> bool:
    """设置预览模块状态 - preview命名空间"""
    try:
        full_key = f"preview.{key}"
        st.session_state[full_key] = value
        return True
    except Exception as e:
        logger.error(f"设置预览状态失败: {e}")
        return False


def get_all_preview_data(cache_key: Optional[str] = None) -> dict:
    """
    获取所有预览数据

    Args:
        cache_key: 缓存键(通常是文件名)，用于验证数据来源

    Returns:
        dict: 包含所有频率数据的字典，如{'日度': df, '周度': df, ...}
    """
    # 如果指定了cache_key，验证当前加载的文件是否匹配
    if cache_key:
        loaded_file = get_preview_state('data_loaded_files')
        if loaded_file != cache_key:
            return {}

    # 收集所有频率的数据
    all_data = {}
    frequencies = ['daily', 'weekly', 'ten_day', 'monthly', 'yearly']
    freq_names = ['日度', '周度', '旬度', '月度', '年度']

    for freq_key, freq_name in zip(frequencies, freq_names):
        df = get_preview_state(f'{freq_key}_df')
        if df is not None and not df.empty:
            all_data[freq_name] = df

    return all_data


def clear_preview_data() -> bool:
    """
    清理所有预览模块的数据

    Returns:
        bool: 是否成功清理
    """
    return clear_state_by_prefix("preview.")


def get_exploration_state(key: str, default: Any = None) -> Any:
    """获取探索模块状态 - exploration命名空间"""
    full_key = f"exploration.{key}"
    return st.session_state.get(full_key, default)


def set_exploration_state(key: str, value: Any) -> bool:
    """设置探索模块状态 - exploration命名空间"""
    try:
        full_key = f"exploration.{key}"
        st.session_state[full_key] = value
        return True
    except Exception as e:
        logger.error(f"设置探索状态失败: {e}")
        return False


# === 按钮状态管理（从button_state_manager迁移）===

def clear_button_state_cache() -> None:
    """清除UI缓存 - 简化版本"""
    cache_prefix = "ui.cache"
    keys_to_delete = [k for k in st.session_state.keys() if str(k).startswith(cache_prefix)]
    for k in keys_to_delete:
        del st.session_state[k]


# === 导出的公共接口 ===

__all__ = [
    # 命名空间
    'StateNamespace',
    # 基础接口
    'get_state',
    'set_state',
    'clear_state_by_prefix',
    # 常用辅助函数
    'get_staged_data',
    # Preview模块专用
    'get_preview_state',
    'set_preview_state',
    'get_all_preview_data',
    'clear_preview_data',
    # Exploration模块专用
    'get_exploration_state',
    'set_exploration_state',
    # 按钮状态管理
    'clear_button_state_cache',
]
