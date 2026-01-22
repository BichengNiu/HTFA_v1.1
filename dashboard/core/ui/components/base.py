# -*- coding: utf-8 -*-
"""
UI组件基类
提供所有UI组件的基础接口和通用功能
"""

import streamlit as st
from typing import List, Dict, Any
from abc import ABC, abstractmethod
import logging
import time

from dashboard.core.ui.utils.error_handler import get_ui_error_handler

logger = logging.getLogger(__name__)


class UIComponent(ABC):
    """
    UI组件基类 - 使用命名空间管理状态

    所有UI组件都应该继承此基类，自动获得命名空间状态管理功能
    """

    def __init__(self, component_name: str = None):
        """初始化UI组件"""
        self.component_name = component_name or self.__class__.__name__
        self.logger = logging.getLogger(f"UI.{self.component_name}")
        self.component_id = self._generate_component_id()

    def _generate_component_id(self) -> str:
        """生成组件ID - 移除Component后缀，转换为小写"""
        class_name = self.__class__.__name__
        if class_name.endswith('Component'):
            class_name = class_name[:-9]
        return class_name.lower()

    # === 状态管理方法 ===

    def get_state(self, key: str, default=None):
        """获取组件状态"""
        full_key = f"ui.{self.component_id}.{key}"
        return st.session_state.get(full_key, default)

    def set_state(self, key: str, value) -> bool:
        """设置组件状态"""
        try:
            full_key = f"ui.{self.component_id}.{key}"
            st.session_state[full_key] = value
            self.logger.debug(f"状态设置成功: {key}")
            return True
        except Exception as e:
            self.logger.error(f"状态设置失败: {key}, 错误: {e}")
            return False

    def get_all_states(self) -> Dict[str, Any]:
        """获取组件的所有状态"""
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
        """清理组件状态"""
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

    # === 渲染方法 ===

    @abstractmethod
    def render(self, st_obj, **kwargs) -> None:
        """
        渲染组件 - 子类必须实现

        Args:
            st_obj: Streamlit对象
            **kwargs: 其他参数
        """
        pass

    @abstractmethod
    def get_state_keys(self) -> List[str]:
        """
        获取组件相关的状态键 - 子类必须实现

        Returns:
            List[str]: 状态键列表
        """
        pass

    # === 错误处理方法 ===

    def handle_error(self, st_obj, error: Exception, context: str = "", **kwargs):
        """
        统一错误处理 - 使用标准化的UI错误处理器

        Args:
            st_obj: Streamlit对象
            error: 异常对象
            context: 错误上下文
            **kwargs: 额外参数
        """
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

    # === 清理方法 ===

    def cleanup(self):
        """组件清理 - 在组件销毁时调用，清理相关状态和资源"""
        try:
            prefix = f"ui.{self.component_id}."
            keys_to_delete = [k for k in st.session_state.keys() if k.startswith(prefix)]
            for k in keys_to_delete:
                del st.session_state[k]
            self.logger.debug(f"组件清理完成: {self.component_id}")
        except Exception as e:
            self.logger.error(f"组件清理失败: {self.component_id}, 错误: {e}")

    # === 组件属性验证方法 ===

    def validate_props(self, props: Dict[str, Any]) -> bool:
        """验证组件属性"""
        return True


__all__ = [
    'UIComponent'
]
