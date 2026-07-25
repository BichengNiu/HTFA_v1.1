# -*- coding: utf-8 -*-
"""
单变量分析页面
包含平稳性检验和结构突变检验功能
"""

import streamlit as st
import logging

from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file
from dashboard.explore.ui.data_overview import render_data_overview
from dashboard.explore.ui.stationarity import StationarityAnalysisComponent
from dashboard.explore.ui.structural_break import (
    StructuralBreakAnalysisComponent,
)

logger = logging.getLogger(__name__)


def render_univariate_analysis_page():
    """渲染单变量分析页面"""
    overview_tab, stationarity_tab, structural_break_tab = st.tabs(
        ["数据概览", "平稳性检验", "结构突变检验"]
    )
    uploaded_file = get_shared_dataset_file()

    with overview_tab:
        render_data_overview(st, uploaded_file)

    with stationarity_tab:
        stationarity_component = StationarityAnalysisComponent()
        stationarity_component.render(st, tab_index=1, uploaded_file=uploaded_file)

    with structural_break_tab:
        structural_break_component = StructuralBreakAnalysisComponent()
        structural_break_component.render(st, tab_index=2, uploaded_file=uploaded_file)
