# -*- coding: utf-8 -*-
"""
状态管理辅助函数模块（简化版）
提供项目实际使用的命名空间状态接口。
"""

import streamlit as st
from typing import Any
import logging

logger = logging.getLogger(__name__)


# === 通用命名空间状态管理器 ===

class NamespacedStateManager:
    """通用命名空间状态管理器，消除重复的状态封装"""

    def __init__(self, namespace: str):
        self.namespace = namespace

    def get(self, key: str, default: Any = None) -> Any:
        full_key = f"{self.namespace}.{key}"
        return st.session_state.get(full_key, default)

    def set(self, key: str, value: Any) -> None:
        full_key = f"{self.namespace}.{key}"
        st.session_state[full_key] = value

    def delete(self, key: str) -> None:
        full_key = f"{self.namespace}.{key}"
        if full_key in st.session_state:
            del st.session_state[full_key]

    def has(self, key: str) -> bool:
        full_key = f"{self.namespace}.{key}"
        return full_key in st.session_state

    def clear_namespace(self) -> None:
        prefix = f'{self.namespace}.'
        keys_to_delete = [k for k in st.session_state.keys() if k.startswith(prefix)]
        for k in keys_to_delete:
            del st.session_state[k]


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


def get_preview_state(
    key: str,
    default: Any = None,
    *,
    namespace: str = "preview",
) -> Any:
    """获取预览模块状态，支持按子模块隔离命名空间。"""
    full_key = f"{namespace}.{key}"
    return st.session_state.get(full_key, default)


def set_preview_state(
    key: str,
    value: Any,
    *,
    namespace: str = "preview",
) -> bool:
    """设置预览模块状态，支持按子模块隔离命名空间。"""
    try:
        full_key = f"{namespace}.{key}"
        st.session_state[full_key] = value
        return True
    except Exception as e:
        logger.error(f"设置预览状态失败: {e}")
        return False


def clear_preview_data(*, namespace: str = "preview") -> bool:
    """
    清理所有预览模块的数据

    Returns:
        bool: 是否成功清理
    """
    return clear_state_by_prefix(f"{namespace}.")


__all__ = [
    "NamespacedStateManager",
    "clear_state_by_prefix",
    "get_preview_state",
    "set_preview_state",
    "clear_preview_data",
]
