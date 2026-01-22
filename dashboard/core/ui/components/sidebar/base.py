# -*- coding: utf-8 -*-
"""
侧边栏基类
提供侧边栏组件的基础接口
"""

import streamlit as st
import logging
from typing import List, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SidebarComponent(ABC):
    """侧边栏组件基类"""

    def __init__(self):
        self.logger = logging.getLogger(f"Sidebar.{self.__class__.__name__}")

    @abstractmethod
    def render(self, st_obj, **kwargs):
        """
        渲染侧边栏内容

        Args:
            st_obj: Streamlit对象
            **kwargs: 其他参数

        Returns:
            渲染结果
        """
        pass

    @abstractmethod
    def get_state_keys(self) -> List[str]:
        """获取组件相关的状态键"""
        pass
