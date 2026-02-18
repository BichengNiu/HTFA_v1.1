# -*- coding: utf-8 -*-
"""
UI组件基类
提供所有UI组件的基础接口和通用功能

架构：UIComponent = 最小基类 + StatefulMixin + ErrorHandlingMixin
子类无需修改，继续继承 UIComponent 即可。
"""

import streamlit as st
from typing import List, Dict, Any
from abc import ABC, abstractmethod
import logging

from dashboard.core.ui.utils.error_handler import get_ui_error_handler

logger = logging.getLogger(__name__)


class StatefulMixin:
    """状态管理 Mixin：get_state/set_state/clear_state/get_all_states"""

    def get_state(self, key: str, default=None):
        full_key = f"ui.{self.component_id}.{key}"
        return st.session_state.get(full_key, default)

    def set_state(self, key: str, value) -> bool:
        try:
            full_key = f"ui.{self.component_id}.{key}"
            st.session_state[full_key] = value
            return True
        except Exception as e:
            self.logger.error(f"状态设置失败: {key}, 错误: {e}")
            return False

    def get_all_states(self) -> Dict[str, Any]:
        try:
            prefix = f"ui.{self.component_id}."
            return {
                key[len(prefix):]: value
                for key, value in st.session_state.items()
                if key.startswith(prefix)
            }
        except Exception as e:
            self.logger.error(f"获取组件所有状态失败: {self.component_id}, 错误: {e}")
            return {}

    def clear_state(self, key: str = None) -> bool:
        try:
            if key:
                full_key = f"ui.{self.component_id}.{key}"
                if full_key in st.session_state:
                    del st.session_state[full_key]
            else:
                prefix = f"ui.{self.component_id}."
                keys_to_delete = [k for k in st.session_state.keys() if str(k).startswith(prefix)]
                for k in keys_to_delete:
                    del st.session_state[k]
            return True
        except Exception as e:
            self.logger.error(f"清理组件状态失败: {key}, 错误: {e}")
            return False


class ErrorHandlingMixin:
    """错误处理 Mixin：handle_error"""

    def handle_error(self, st_obj, error: Exception, context: str = "", **kwargs):
        try:
            error_handler = get_ui_error_handler()
            result = error_handler.handle_ui_error(
                error=error,
                component_id=self.component_id,
                context=context,
                st_obj=st_obj,
                **kwargs
            )
            if result.get('success'):
                self.set_state('last_error', result['error_info'])
                self.set_state('error_count', self.get_state('error_count', 0) + 1)
            return result
        except Exception as e:
            self.logger.error(f"标准化错误处理失败: {self.component_id}, 原始错误: {error}, 处理错误: {e}")
            raise RuntimeError(f"组件 {self.component_id} 错误处理失败: {e}") from error


class UIComponent(StatefulMixin, ErrorHandlingMixin, ABC):
    """
    UI组件基类 - 使用命名空间管理状态

    组合 StatefulMixin + ErrorHandlingMixin + ABC
    所有UI组件继承此基类，接口不变。
    """

    def __init__(self, component_name: str = None):
        self.component_name = component_name or self.__class__.__name__
        self.logger = logging.getLogger(f"UI.{self.component_name}")
        self.component_id = self._generate_component_id()

    def _generate_component_id(self) -> str:
        class_name = self.__class__.__name__
        if class_name.endswith('Component'):
            class_name = class_name[:-9]
        return class_name.lower()

    @abstractmethod
    def render(self, st_obj, **kwargs) -> None:
        pass

    @abstractmethod
    def get_state_keys(self) -> List[str]:
        pass

    def cleanup(self):
        self.clear_state()

    def validate_props(self, props: Dict[str, Any]) -> bool:
        return True


__all__ = ['UIComponent', 'StatefulMixin', 'ErrorHandlingMixin']
