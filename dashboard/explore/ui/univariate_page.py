# -*- coding: utf-8 -*-
"""
时序性质页面
包含平稳性分析功能
"""

import streamlit as st
import logging

from dashboard.explore.ui.stationarity import StationarityAnalysisComponent

logger = logging.getLogger(__name__)


def render_univariate_analysis_page():
    """渲染时序性质页面"""
    # 创建平稳性分析标签页
    tab = st.tabs(["平稳性分析"])[0]

    with tab:
        # 渲染分析组件（组件内部包含数据上传功能）
        stationarity_component = StationarityAnalysisComponent()
        stationarity_component.render(st, tab_index=0)
