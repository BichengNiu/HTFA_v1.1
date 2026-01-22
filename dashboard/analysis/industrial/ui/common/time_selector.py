# -*- coding: utf-8 -*-
"""
工业分析时间范围选择器组件
"""

import streamlit as st
from typing import Optional, Tuple
from dashboard.core.ui.components.base import UIComponent


class IndustrialTimeRangeSelectorComponent(UIComponent):
    """工业分析时间范围选择器组件"""

    def __init__(self):
        super().__init__()

    def render(self, st_obj, key_suffix: str = "", default_index: int = 3, **kwargs) -> Tuple[str, Optional[str], Optional[str]]:
        """
        渲染时间范围选择器

        Args:
            st_obj: Streamlit对象
            key_suffix: 键后缀，用于区分不同的选择器实例
            default_index: 默认选择的索引

        Returns:
            Tuple[时间范围, 自定义开始时间, 自定义结束时间]
        """
        time_range = st_obj.radio(
            "时间范围",
            ["1年", "3年", "5年", "全部", "自定义"],
            index=default_index,
            horizontal=True,
            key=f"macro_time_range_{key_suffix}"
        )

        custom_start = None
        custom_end = None
        if time_range == "自定义":
            col_start, col_end = st_obj.columns([1, 1])
            with col_start:
                custom_start = st_obj.text_input("开始年月", placeholder="2020-01", key=f"custom_start_{key_suffix}")
            with col_end:
                custom_end = st_obj.text_input("结束年月", placeholder="2024-12", key=f"custom_end_{key_suffix}")

        return time_range, custom_start, custom_end

    def get_state_keys(self) -> list:
        """获取组件相关的状态键"""
        return [
            'macro_time_range_*',
            'custom_start_*',
            'custom_end_*'
        ]
