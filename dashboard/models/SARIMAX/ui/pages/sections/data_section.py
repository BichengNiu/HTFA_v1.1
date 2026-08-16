"""SARIMAX 工作流 - ① 数据导入环节。"""

from __future__ import annotations

import logging

import streamlit as st

from dashboard.models.SARIMAX.core.data_loader import (
    load_modeling_dataset,
    numeric_variable_names,
)
from dashboard.models.SARIMAX.ui.state import (
    WIDGET_KEYS,
    clear_dataset_state,
    clear_fit_results,
    clear_widget_state,
    state,
)

logger = logging.getLogger(__name__)


def render_data_import_section(st_obj) -> None:
    """上传数据文件并选择目标/外生变量。"""
    st_obj.markdown("#### ① 数据导入")
    uploaded_file = st_obj.file_uploader(
        "选择数据文件（CSV / XLSX / XLS）",
        type=["csv", "xlsx", "xls"],
        key="sarimax_file_uploader",
        help=(
            "第一列若为日期将被解析为时间索引；其余列应为数值型指标。"
            "更换文件会清除已配置的变量选择与拟合结果。"
        ),
    )
    if uploaded_file is None:
        if state.get("file_fingerprint") is not None:
            clear_dataset_state()
            clear_widget_state(st_obj)
        st_obj.info("请上传包含时间序列数据的文件。")
        return

    fingerprint = state.get("file_fingerprint")
    if fingerprint is None or fingerprint != _content_fingerprint(uploaded_file):
        try:
            dataset = load_modeling_dataset(uploaded_file)
        except Exception as exc:  # noqa: BLE001 - 用户可读的文件解析边界
            st_obj.error(f"文件读取失败：{exc}")
            logger.exception("SARIMAX 数据文件解析失败")
            return
        state.set("dataset", dataset)
        state.set("file_fingerprint", dataset.fingerprint)
        state.set("file_name", dataset.file_name)
        state.set("target_variable", None)
        state.set("exog_variables", ())
        clear_fit_results()
        clear_widget_state(st_obj, WIDGET_KEYS[1:])

    dataset = state.get("dataset")
    if dataset is None:
        st_obj.error("数据集加载失败，请重新上传文件。")
        return

    st_obj.success(f"已加载：{dataset.file_name}")
    time_text = ""
    if dataset.time_column is not None:
        series = dataset.frame[dataset.time_column]
        time_text = (
            f" · 时间范围 {series.min():%Y-%m-%d} ~ {series.max():%Y-%m-%d}"
        )
    st_obj.caption(
        f"{dataset.frame.shape[0]:,} 行 × {dataset.frame.shape[1]:,} 列"
        f"{time_text}"
    )
    st_obj.dataframe(dataset.frame.head(8), width="stretch")

    variables = numeric_variable_names(dataset.frame)
    if not variables:
        st_obj.error("数据中没有可用的数值型变量。")
        return

    st_obj.markdown("**变量选择**")
    select_columns = st_obj.columns(2)
    with select_columns[0]:
        target = st_obj.selectbox(
            "目标变量（因变量，将被建模的序列）",
            options=variables,
            key="sarimax_target_select",
        )
    if target != state.get("target_variable"):
        state.set("target_variable", target)
        state.set("exog_variables", ())
        clear_fit_results()
        clear_widget_state(st_obj, ("sarimax_exog_select",))

    with select_columns[1]:
        exog_options = [name for name in variables if name != target]
        exog = st_obj.multiselect(
            "外生变量（可选，作为回归输入参与建模）",
            options=exog_options,
            key="sarimax_exog_select",
            help="外生变量的观测日期必须与目标变量完全对齐。",
        )
    if tuple(exog) != state.get("exog_variables", ()):
        state.set("exog_variables", tuple(exog))
        clear_fit_results()

    st_obj.caption(
        f"当前配置：目标变量「{target}」，外生变量 "
        + (f"「{'、'.join(exog)}」" if exog else "无")
    )


def _content_fingerprint(uploaded_file) -> str:
    """读取上传文件内容指纹（避免依赖已缓存对象的状态）。"""
    from dashboard.core.ui.utils.shared_dataset import fingerprint_file

    return fingerprint_file(uploaded_file)


__all__ = ["render_data_import_section"]
