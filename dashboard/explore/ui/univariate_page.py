"""
单变量分析页面
包含平稳性检验和结构突变检验功能
"""

import logging

import streamlit as st

from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file
from dashboard.core.workspace import SessionWorkspace
from dashboard.explore.ui.data_overview import render_data_overview
from dashboard.explore.ui.dataset_context import get_explore_dataset
from dashboard.explore.ui.stationarity import StationarityAnalysisComponent
from dashboard.explore.ui.structural_break import (
    StructuralBreakAnalysisComponent,
)

logger = logging.getLogger(__name__)

_PAGE_ID = "exploration.univariate"
_PERSISTENT_KEYS = (
    "data_overview_table_select",
    "data_overview_variable_select",
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
)
_PERSISTENT_PREFIXES = ("tools.analysis.chart_config.",)


def render_univariate_analysis_page():
    """渲染单变量分析页面"""
    workspace = SessionWorkspace(st.session_state)
    workspace.begin_page(
        _PAGE_ID, keys=_PERSISTENT_KEYS, prefixes=_PERSISTENT_PREFIXES
    )
    try:
        uploaded_file = get_shared_dataset_file()
        try:
            dataset = get_explore_dataset(st, uploaded_file)
        except Exception as exc:  # noqa: BLE001 - user-facing file load boundary
            st.error(f"文件读取或数据库解析失败：{exc}")
            return

        overview_tab, stationarity_tab, structural_break_tab = st.tabs(
            ["数据概览", "平稳性检验", "结构突变检验"]
        )

        with overview_tab:
            render_data_overview(st, uploaded_file, dataset=dataset)

        with stationarity_tab:
            stationarity_component = StationarityAnalysisComponent()
            stationarity_component.render(
                st,
                uploaded_file=uploaded_file,
                dataset=dataset,
            )

        with structural_break_tab:
            structural_break_component = StructuralBreakAnalysisComponent()
            structural_break_component.render(
                st,
                uploaded_file=uploaded_file,
                dataset=dataset,
            )
    finally:
        workspace.end_page(_PAGE_ID)
