# -*- coding: utf-8 -*-
"""
时序关系页面
包含同步分析和领先滞后分析功能
"""

import streamlit as st
import pandas as pd
import logging
from typing import Optional

from dashboard.explore.ui.unified_correlation import UnifiedCorrelationAnalysisComponent
from dashboard.explore.ui.lead_lag import LeadLagAnalysisComponent
from dashboard.core.ui.components.data_input import UnifiedDataUploadComponent
from dashboard.explore.core.series_utils import clean_dataframe_columns

logger = logging.getLogger(__name__)


def render_bivariate_analysis_page():
    """渲染时序关系页面"""
    # 权限过滤
    debug_mode = st.session_state.get("auth.debug_mode", False)
    current_user = st.session_state.get("auth.current_user", None)

    # 定义所有Tab及其对应的权限
    all_tabs_info = [
        ("同步分析", "data_exploration.bivariate.correlation"),
        ("领先滞后分析", "data_exploration.bivariate.lead_lag")
    ]

    # 过滤Tab
    if debug_mode or not current_user:
        visible_tabs = all_tabs_info
    else:
        from dashboard.auth.ui.middleware import get_auth_middleware
        auth_middleware = get_auth_middleware()

        visible_tabs = []
        for tab_name, permission_code in all_tabs_info:
            if auth_middleware.permission_manager.has_granular_access(
                current_user, "数据探索", "时序关系", tab_name
            ):
                visible_tabs.append((tab_name, permission_code))

    # 如果没有可访问的Tab
    if not visible_tabs:
        st.warning("您没有权限访问任何Tab")
        return

    # 创建可见的标签页
    tab_names = [tab[0] for tab in visible_tabs]
    tabs = st.tabs(tab_names)

    # 渲染Tab
    for i, (tab_name, permission_code) in enumerate(visible_tabs):
        with tabs[i]:
            if tab_name == "同步分析":
                _render_correlation_tab()
            elif tab_name == "领先滞后分析":
                _render_lead_lag_tab()


def _render_correlation_tab():
    """渲染同步分析Tab"""
    with st.container():
        # Tab内数据上传 - 同步分析
        st.markdown("#### 上传数据")
        upload_component_corr = UnifiedDataUploadComponent(
            accepted_types=['csv', 'xlsx', 'xls'],
            help_text="上传CSV或Excel文件进行相关性分析",
            show_data_source_selector=False,
            show_staging_data_option=False,
            component_id="bivariate_correlation_upload"
        )

        data_corr = upload_component_corr.render_file_upload_section(
            st,
            upload_key="correlation_tab_upload",
            show_overview=False,
            show_preview=False
        )

        if data_corr is not None:
            clean_dataframe_columns(data_corr)
            file_name_corr = upload_component_corr.get_state('file_name')
            st.session_state['exploration.time_lag_corr.upload_data'] = data_corr
            st.session_state['exploration.time_lag_corr.file_name'] = file_name_corr
            st.success(f"数据已加载: {file_name_corr} ({data_corr.shape[0]} 行 x {data_corr.shape[1]} 列)")

        correlation_component = UnifiedCorrelationAnalysisComponent()
        correlation_component.render(st, tab_index=0)


def _render_lead_lag_tab():
    """渲染领先滞后分析Tab"""
    with st.container():
        # Tab内数据上传 - 领先滞后分析
        upload_component_lag = UnifiedDataUploadComponent(
            accepted_types=['csv', 'xlsx', 'xls'],
            help_text="上传CSV或Excel文件进行领先滞后分析",
            show_data_source_selector=False,
            show_staging_data_option=False,
            component_id="bivariate_lead_lag_upload"
        )

        data_lag = upload_component_lag.render_file_upload_section(
            st,
            upload_key="lead_lag_tab_upload",
            show_overview=False,
            show_preview=False
        )

        if data_lag is not None:
            clean_dataframe_columns(data_lag)
            file_name_lag = upload_component_lag.get_state('file_name')
            st.session_state['exploration.lead_lag.upload_data'] = data_lag
            st.session_state['exploration.lead_lag.file_name'] = file_name_lag
            st.success(f"数据已加载: {file_name_lag} ({data_lag.shape[0]} 行 x {data_lag.shape[1]} 列)")
            st.divider()

        lead_lag_component = LeadLagAnalysisComponent()
        lead_lag_component.render(st, tab_index=1)
