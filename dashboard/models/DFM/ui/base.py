# -*- coding: utf-8 -*-
"""
DFM UI组件基类

为DFM相关UI组件提供统一的验证和错误处理接口
"""

from typing import Dict
from abc import abstractmethod

# 导入基础UI组件
from dashboard.core.ui.components.base import UIComponent


class DFMComponent(UIComponent):
    """
    DFM组件基类

    为DFM相关UI组件提供统一的验证和错误处理接口，
    所有DFM组件必须实现这两个方法以确保一致的用户体验
    """

    def get_state_key_prefix(self) -> str:
        """
        获取组件状态键前缀，用于生成唯一的Streamlit组件key

        Returns:
            str: 状态键前缀
        """
        return f"dfm_{self.get_component_id().lower()}"

    @abstractmethod
    def validate_input(self, data: Dict) -> bool:
        """
        验证输入数据

        Args:
            data: 输入数据字典

        Returns:
            bool: 验证是否通过
        """
        pass

    @abstractmethod
    def handle_service_error(self, error: Exception) -> None:
        """
        处理服务错误

        Args:
            error: 异常对象
        """
        pass


__all__ = [
    'DFMComponent'
]
