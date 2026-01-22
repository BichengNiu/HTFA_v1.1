# -*- coding: utf-8 -*-
"""
时间序列分析组件基类
提供时间序列分析组件的基础接口和通用功能
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from abc import abstractmethod
import logging
import time

from dashboard.core.ui.components.base import UIComponent
from dashboard.core.ui.utils.state_helpers import (
    get_exploration_state,
    set_exploration_state
)

logger = logging.getLogger(__name__)


class TimeSeriesAnalysisComponent(UIComponent):
    """时间序列分析组件基类"""

    def __init__(self, analysis_type: str, title: str = None):
        # 先设置属性
        self.analysis_type = analysis_type
        self.title = title or analysis_type
        self.logger = logging.getLogger(f"{__name__}.{analysis_type}")

        # 调用父类初始化方法
        super().__init__(component_name=f"timeseries_{analysis_type}")

    def get_component_id(self) -> str:
        """获取组件ID"""
        return f"timeseries_{self.analysis_type}"

    def get_state_keys(self) -> List[str]:
        """获取组件相关的状态键"""
        return [
            f'{self.analysis_type}_data',
            f'{self.analysis_type}_results',
            f'{self.analysis_type}_parameters',
            f'{self.analysis_type}_last_analysis_time',
            f'{self.analysis_type}_active'
        ]

    def get_state(self, key: str, default=None):
        """获取分析状态"""
        import streamlit as st
        state_key = f'tools.analysis.{self.analysis_type}.{key}'
        return st.session_state.get(state_key, default)

    def set_state(self, key: str, value):
        """设置分析状态"""
        import streamlit as st
        state_key = f'tools.analysis.{self.analysis_type}.{key}'
        try:
            st.session_state[state_key] = value
            return True
        except Exception:
            return False

    def set_state_value(self, key: str, value):
        """设置状态值"""
        import streamlit as st
        state_key = f'tools.ui_state.{key}'
        try:
            st.session_state[state_key] = value
        except Exception:
            self.logger.debug(f"Failed to set UI state: {key}")

    def get_session_state_value(self, key: str, default=None):
        """获取session state值"""
        import streamlit as st
        state_key = f'tools.ui_state.session.{key}'
        value = st.session_state.get(state_key, None)
        return value if value is not None else default

    def detect_tab_activation(self, st_obj, tab_index: int) -> bool:
        """
        检测当前标签页是否激活

        Args:
            st_obj: Streamlit对象
            tab_index: 标签页索引

        Returns:
            bool: 是否激活
        """
        is_really_active = False

        import streamlit as st

        # 检查管理的标签页状态
        current_active_tab = st.session_state.get('tools.ui_state.data_exploration_active_tab')
        is_really_active = (current_active_tab == self.analysis_type)

        # 只在状态真正改变时才更新
        if is_really_active:
            previous_active_tab = self.get_session_state_value('data_exploration_active_tab', None)

            if previous_active_tab != self.analysis_type:
                self.logger.debug(f"Tab {self.analysis_type} activated")

                # 批量设置状态以减少调用次数
                self.set_state_value(f'currently_in_{self.analysis_type}_tab', True)
                self.set_state_value('data_exploration_active_tab', self.analysis_type)

                # 只在标签页切换时更新时间戳，避免每次渲染都更新
                self.set_state('last_activity_time', time.time())

        return is_really_active

    def get_module_data(self) -> Tuple[Optional[pd.DataFrame], str, str]:
        """
        获取当前模块的数据

        Returns:
            Tuple[Optional[pd.DataFrame], str, str]: (数据, 数据源描述, 数据名称)
        """
        self.logger.debug(f"Getting module data for analysis type: {self.analysis_type}")

        # 从tab内上传的独立数据读取
        data_key = f"exploration.{self.analysis_type}.upload_data"
        file_name_key = f"exploration.{self.analysis_type}.file_name"

        selected_data = st.session_state.get(data_key)

        if selected_data is not None:
            file_name = st.session_state.get(file_name_key, '')

            self.logger.debug(f"Found data with shape: {selected_data.shape}, file: {file_name}")

            data_source = f"上传文件: {file_name}" if file_name else "上传文件"
            selected_df_name = file_name or "data"
            return selected_data, data_source, selected_df_name
        else:
            self.logger.debug(f"No data found for module: {self.analysis_type}")
            return None, "未选择数据", ""

    def render_data_status(self, st_obj):
        """渲染数据状态信息"""
        selected_data, data_source, selected_df_name = self.get_module_data()

        if selected_data is None:
            st_obj.info("请在上方上传数据文件以进行分析")
            st_obj.markdown("""
            **使用说明：**
            1. **数据上传**：在上方区域上传CSV或Excel文件
            2. **数据格式**：第一列为时间戳，其余列为变量数据
            3. **支持格式**：CSV、Excel (.xlsx, .xls)
            4. **数据隔离**：每个tab的数据独立管理，切换tab时数据保留
            """)
            return None, "", ""
        else:
            return selected_data, data_source, selected_df_name

    @abstractmethod
    def render_analysis_interface(self, st_obj, data: pd.DataFrame, data_name: str) -> Any:
        """
        渲染分析界面

        Args:
            st_obj: Streamlit对象
            data: 分析数据
            data_name: 数据名称

        Returns:
            Any: 分析结果
        """
        pass

    def render(self, st_obj, **kwargs) -> Any:
        """
        渲染完整的时间序列分析组件

        Args:
            st_obj: Streamlit对象
            **kwargs: 其他参数

        Returns:
            Any: 分析结果
        """
        try:
            # 检测标签页激活状态
            tab_index = kwargs.get('tab_index', 0)
            self.detect_tab_activation(st_obj, tab_index)

            # 移除重复的标题渲染，因为标签页已经显示了标题
            # st_obj.markdown(f"### {self.title}")

            # 渲染数据状态和获取数据
            data, data_source, data_name = self.render_data_status(st_obj)

            if data is None:
                return None

            # 渲染分析界面
            return self.render_analysis_interface(st_obj, data, data_name)

        except Exception as e:
            self.handle_error(st_obj, e, f"渲染{self.title}组件")
            return None


__all__ = ['TimeSeriesAnalysisComponent']
