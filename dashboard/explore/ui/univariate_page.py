# -*- coding: utf-8 -*-
"""
时序性质页面
包含平稳性检验和结构突变检验功能
"""

import streamlit as st
import logging

from dashboard.explore.ui.stationarity import StationarityAnalysisComponent
from dashboard.explore.ui.structural_break import (
    StructuralBreakAnalysisComponent,
)

logger = logging.getLogger(__name__)


def render_univariate_analysis_page():
    """渲染时序性质页面"""
    stationarity_tab, structural_break_tab = st.tabs(
        ["平稳性检验", "结构突变检验"]
    )

    with stationarity_tab:
        # 渲染分析组件（组件内部包含数据上传功能）
        stationarity_component = StationarityAnalysisComponent()
        stationarity_component.render(st, tab_index=0)

    with structural_break_tab:
        structural_break_component = StructuralBreakAnalysisComponent()
        structural_break_component.render(st, tab_index=1)
