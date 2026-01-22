"""
统一状态管理模块
Unified State Management Module

提供工业分析模块的集中状态管理，消除重复的状态封装函数
"""

import streamlit as st
from typing import Any, Optional


class IndustrialStateManager:
    """
    工业分析模块统一状态管理器

    使用点分命名空间管理状态，避免键冲突
    命名空间: industrial.analysis
    """

    NAMESPACE = "industrial.analysis"

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        获取状态值

        Args:
            key: 状态键
            default: 默认值

        Returns:
            状态值，如果不存在则返回默认值
        """
        full_key = f"{cls.NAMESPACE}.{key}"
        return st.session_state.get(full_key, default)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """
        设置状态值

        Args:
            key: 状态键
            value: 状态值
        """
        full_key = f"{cls.NAMESPACE}.{key}"
        st.session_state[full_key] = value

    @classmethod
    def delete(cls, key: str) -> None:
        """
        删除状态值

        Args:
            key: 状态键
        """
        full_key = f"{cls.NAMESPACE}.{key}"
        if full_key in st.session_state:
            del st.session_state[full_key]

    @classmethod
    def has(cls, key: str) -> bool:
        """
        检查状态键是否存在

        Args:
            key: 状态键

        Returns:
            是否存在
        """
        full_key = f"{cls.NAMESPACE}.{key}"
        return full_key in st.session_state
