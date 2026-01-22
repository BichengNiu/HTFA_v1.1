# -*- coding: utf-8 -*-
"""
状态管理器包装类
为组件提供统一的状态访问接口
"""

import streamlit as st
from typing import Any, Optional


class StateManager:
    """状态管理器包装类"""

    def __init__(self, namespace: str = 'train_model'):
        """
        初始化状态管理器

        Args:
            namespace: 状态命名空间
        """
        self.namespace = namespace

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取状态值

        Args:
            key: 状态键名
            default: 默认值

        Returns:
            状态值或默认值
        """
        full_key = f'{self.namespace}.{key}'
        return st.session_state.get(full_key, default)

    def set(self, key: str, value: Any) -> None:
        """
        设置状态值

        Args:
            key: 状态键名
            value: 状态值
        """
        full_key = f'{self.namespace}.{key}'
        st.session_state[full_key] = value

    def delete(self, key: str) -> None:
        """
        删除状态键

        Args:
            key: 状态键名
        """
        full_key = f'{self.namespace}.{key}'
        if full_key in st.session_state:
            del st.session_state[full_key]

    def exists(self, key: str) -> bool:
        """
        检查状态键是否存在

        Args:
            key: 状态键名

        Returns:
            是否存在
        """
        full_key = f'{self.namespace}.{key}'
        return full_key in st.session_state

    def clear_namespace(self) -> None:
        """清除当前命名空间下的所有状态"""
        prefix = f'{self.namespace}.'
        keys_to_delete = [key for key in st.session_state.keys() if key.startswith(prefix)]
        for key in keys_to_delete:
            del st.session_state[key]
