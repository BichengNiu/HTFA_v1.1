"""
多变量分析页面
包含同步分析和领先滞后分析功能
"""

import logging
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.core.ui.utils.shared_dataset import (
    get_shared_dataset_file,
)
from dashboard.explore.core.data_source import ExploreDataset, format_table_option
from dashboard.explore.core.series_utils import clean_dataframe_columns
from dashboard.explore.ui.dataset_context import get_explore_dataset
from dashboard.explore.ui.dtw import DTWAnalysisComponent
from dashboard.explore.ui.lead_lag import LeadLagAnalysisComponent

logger = logging.getLogger(__name__)
TAB_NAMES = ("同步分析", "领先滞后分析")


def _visible_tab_names() -> list[str]:
    debug_mode = st.session_state.get("auth.debug_mode", False)
    current_user = st.session_state.get("auth.current_user", None)
    if debug_mode or not current_user:
        return list(TAB_NAMES)

    from dashboard.auth.ui.middleware import get_auth_middleware

    permission_manager = get_auth_middleware().permission_manager
    return [
        tab_name
        for tab_name in TAB_NAMES
        if permission_manager.check_granular_access(
            current_user,
            "数据探索",
            "多变量分析",
            tab_name,
        )
    ]


def _load_dataset(uploaded_file: Any) -> ExploreDataset | None:
    try:
        dataset = get_explore_dataset(st, uploaded_file)
    except Exception as exc:  # noqa: BLE001 - user-facing file load boundary
        st.error(f"文件读取或数据库解析失败：{exc}")
        return None

    if not dataset.tables:
        st.error("数据集没有可分析的数据表。")
        return None
    return dataset


def _select_analysis_table(
    dataset: ExploreDataset,
) -> tuple[str, pd.DataFrame] | None:
    selected_table = st.selectbox(
        "选择要分析的数据表",
        options=list(dataset.tables),
        format_func=lambda key: format_table_option(key, dataset.tables),
        key="bivariate_table_select",
    )
    analysis_data = dataset.tables[selected_table].copy()
    clean_dataframe_columns(analysis_data)
    if not analysis_data.columns.is_unique:
        st.error("清理列名后出现重复变量名，请先修正数据文件。")
        return None
    return selected_table, analysis_data


def _publish_analysis_data(
    dataset: ExploreDataset,
    selected_table: str,
    analysis_data: pd.DataFrame,
) -> str:
    data_signature = (dataset.fingerprint, selected_table)
    if st.session_state.get("exploration.bivariate.data_signature") != data_signature:
        _clear_bivariate_results()
        st.session_state["exploration.bivariate.data_signature"] = data_signature

    data_name = f"{dataset.file_name}-{selected_table}"
    st.session_state["exploration.lead_lag.upload_data"] = analysis_data
    st.session_state["exploration.lead_lag.file_name"] = data_name
    st.caption(
        f"当前数据：{dataset.file_name} · "
        f"{format_table_option(selected_table, dataset.tables)}"
    )
    return data_name


def render_bivariate_analysis_page() -> None:
    """渲染多变量分析页面。"""
    visible_tabs = _visible_tab_names()
    if not visible_tabs:
        st.warning("您没有权限访问任何Tab")
        return

    uploaded_file = get_shared_dataset_file()
    if uploaded_file is None:
        st.info("请先在侧边栏上传共享数据集。")
        return

    dataset = _load_dataset(uploaded_file)
    if dataset is None:
        return
    selection = _select_analysis_table(dataset)
    if selection is None:
        return
    selected_table, analysis_data = selection
    data_name = _publish_analysis_data(dataset, selected_table, analysis_data)

    tabs = st.tabs(visible_tabs)
    for index, tab_name in enumerate(visible_tabs):
        with tabs[index]:
            if tab_name == "同步分析":
                _render_correlation_tab(analysis_data, data_name)
            else:
                _render_lead_lag_tab()


def _render_correlation_tab(data: pd.DataFrame, data_name: str) -> None:
    """渲染同步分析Tab"""
    with st.container():
        st.markdown("---")
        st.markdown("#### DTW分析")
        DTWAnalysisComponent().render_analysis_interface(st, data, data_name)


def _render_lead_lag_tab():
    """渲染领先滞后分析Tab"""
    with st.container():
        lead_lag_component = LeadLagAnalysisComponent()
        lead_lag_component.render(st, tab_index=1)


def _clear_bivariate_results() -> None:
    """切换文件或频率表时清除依赖旧数据的结果。"""
    prefixes = (
        "tools.analysis.dtw.",
        "tools.analysis.lead_lag.",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            del st.session_state[key]
