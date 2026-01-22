# -*- coding: utf-8 -*-
"""
工业分析分组详情组件
"""

import streamlit as st
import pandas as pd
import logging
from dashboard.core.ui.components.base import UIComponent

logger = logging.getLogger(__name__)


class IndustrialGroupDetailsComponent(UIComponent):
    """工业分析分组详情组件"""

    def __init__(self):
        super().__init__()

    def render(self, st_obj, df_weights: pd.DataFrame, group_type: str, title: str, **kwargs):
        """
        渲染分组详情展开器

        Args:
            st_obj: Streamlit对象
            df_weights: 权重数据DataFrame
            group_type: 分组类型
            title: 展开器标题
        """
        with st_obj.expander(title):
            group_details = self._get_group_details(df_weights, group_type)
            if not group_details.empty:
                st_obj.dataframe(group_details, width='stretch', hide_index=True)
                st_obj.caption("权重基于2018年投入产出表增加值占比加权计算")
            else:
                st_obj.write("暂无分组数据")

    def _get_group_details(self, df_weights: pd.DataFrame, group_type: str) -> pd.DataFrame:
        """
        获取分组详情数据

        Args:
            df_weights: 权重数据
            group_type: 分组类型

        Returns:
            分组详情DataFrame
        """
        try:
            if group_type in df_weights.columns:
                group_details = df_weights.groupby(group_type).agg({
                    '指标名称': 'count',
                    '权重_2020': 'sum'
                }).rename(columns={
                    '指标名称': '指标数量',
                    '权重_2020': '总权重'
                }).reset_index()
                return group_details
            else:
                return pd.DataFrame()
        except Exception:
            logger.error(f"获取分组详情失败: {group_type}")
            return pd.DataFrame()

    def get_state_keys(self) -> list:
        """获取组件相关的状态键"""
        return []
