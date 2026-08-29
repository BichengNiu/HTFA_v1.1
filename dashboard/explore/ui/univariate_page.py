"""单变量分析页面，包含数据概览、平稳性检验和结构突变检验。"""

from __future__ import annotations

import logging

import streamlit as st

from dashboard.core.ui.utils.shared_dataset import get_shared_dataset_file
from dashboard.core.workspace import SessionWorkspace
from dashboard.explore.ui.data_overview import (
    CORRELOGRAM_TRANSFORMATION_PREFIX,
    DATA_OVERVIEW_HANDOFF_WIDGET_KEYS,
    SERIES_STYLE_WIDGET_PREFIX,
    render_data_overview,
)
from dashboard.explore.ui.standalone_data_overview import (
    create_standalone_data_overview_url,
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
) + DATA_OVERVIEW_HANDOFF_WIDGET_KEYS
_PERSISTENT_PREFIXES = (
    "tools.analysis.chart_config.",
    CORRELOGRAM_TRANSFORMATION_PREFIX,
    SERIES_STYLE_WIDGET_PREFIX,
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
            render_data_overview(st)
            _render_standalone_overview_launcher()

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


def _render_standalone_overview_launcher() -> None:
    """复制当前数据概览状态到不回写原会话的独立页面。"""

    st.markdown("---")
    st.markdown("**复制到独立标签页**")
    st.caption(
        "新页面会复制当前文件、读取设置和已生成图表对应的参数；"
        "之后两边可分别继续操作，互不影响。"
    )
    url = create_standalone_data_overview_url(st)
    if url is None:
        st.info("请先在左侧“共享数据集”上传文件。")
        return
    st.link_button(
        "在新标签页打开数据概览",
        url,
        icon=":material/open_in_new:",
    )
