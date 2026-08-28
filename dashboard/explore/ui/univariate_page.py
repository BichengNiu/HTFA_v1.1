"""单变量分析页面，包含数据概览、平稳性检验和结构突变检验。"""

from __future__ import annotations

import logging

import streamlit as st

from data_overview.ui.widget_keys import overview_widget_keys

from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file
from dashboard.core.workspace import SessionWorkspace
from dashboard.explore.ui.data_overview import (
    CORRELOGRAM_TRANSFORMATION_PREFIX,
    CORRELOGRAM_WIDGET_KEYS,
    render_data_overview,
)
from dashboard.explore.ui.stationarity import StationarityAnalysisComponent
from dashboard.explore.ui.structural_break import StructuralBreakAnalysisComponent

logger = logging.getLogger(__name__)

_PAGE_ID = "exploration.univariate"
_PERSISTENT_KEYS = (
    "stationarity_table_select",
    "stationarity_variable_select",
    "stationarity_test_methods",
    "stationarity_test_alpha",
    "stationarity_date_range",
    "stationarity_transformation_select",
    "stationarity_test_source",
    "stationarity_adf_trend",
    "stationarity_kpss_trend",
    "stationarity_pp_trend",
    "structural_break_table_select",
    "structural_break_variable_select",
    "structural_break_model",
    "structural_break_lag_method",
    "structural_break_alpha",
) + overview_widget_keys("sarimax") + CORRELOGRAM_WIDGET_KEYS
_PERSISTENT_PREFIXES = (
    "tools.analysis.chart_config.",
    CORRELOGRAM_TRANSFORMATION_PREFIX,
)


def render_univariate_analysis_page():
    """渲染单变量分析页面。"""
    workspace = SessionWorkspace(st.session_state)
    workspace.begin_page(
        _PAGE_ID, keys=_PERSISTENT_KEYS, prefixes=_PERSISTENT_PREFIXES
    )
    try:
        uploaded_file = get_shared_dataset_file()

        overview_tab, stationarity_tab, structural_break_tab = st.tabs(
            ["数据概览", "平稳性检验", "结构突变检验"]
        )

        with overview_tab:
            # 动态回归的数据读取设置、数据表和时间序列预览在此统一维护；
            # ACF/PACF 由 render_data_overview 在预览后继续渲染。
            render_data_overview(st)

        with stationarity_tab:
            stationarity_component = StationarityAnalysisComponent()
            stationarity_component.render(
                st,
                uploaded_file=uploaded_file,
            )

        with structural_break_tab:
            structural_break_component = StructuralBreakAnalysisComponent()
            structural_break_component.render(
                st,
                uploaded_file=uploaded_file,
            )
    finally:
        workspace.end_page(_PAGE_ID)
