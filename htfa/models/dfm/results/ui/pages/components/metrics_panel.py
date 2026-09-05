"""DFM 结果摘要指标渲染。"""

import numpy as np
import streamlit as st

from htfa.models.dfm.results.ui.pages.domain import DFMMetadataAccessor


def _render_period_dates(accessor: DFMMetadataAccessor) -> None:
    info = accessor.training_info
    values = (
        ("训练期", info.training_start),
        ("验证期", info.validation_start),
        ("观察期", accessor.observation_period_start),
    )
    for column, (label, value) in zip(st.columns(3), values):
        with column:
            st.metric(label, value if value != "N/A" else "N/A")


def _render_basic_info(accessor: DFMMetadataAccessor) -> None:
    info = accessor.training_info
    values = (
        ("最终行业数", info.n_industries),
        ("最终变量数", info.n_variables),
        ("最终因子数", info.n_factors),
    )
    for column, (label, value) in zip(st.columns(3), values):
        with column:
            display = int(value) if isinstance(value, (int, np.integer)) else "N/A"
            st.metric(label, display)


def _render_error_row(accessor: DFMMetadataAccessor, metric_name: str) -> None:
    formatter = DFMMetadataAccessor.format_metric
    metric_attr = metric_name.lower()
    values = (
        (f"训练期{metric_name}", getattr(accessor.training_metrics, metric_attr)),
        (
            f"验证期{metric_name}",
            getattr(accessor.validation_metrics, metric_attr)
            if accessor.has_valid_validation_metrics
            else None,
        ),
        (
            f"观察期{metric_name}",
            getattr(accessor.observation_metrics, metric_attr)
            if accessor.has_observation_metrics
            else None,
        ),
    )
    for column, (label, value) in zip(st.columns(3), values):
        with column:
            st.metric(label, formatter(value) if value is not None else "N/A")


def render_all_metrics(accessor: DFMMetadataAccessor) -> None:
    """渲染完整结果摘要。"""
    st.markdown("---")
    st.markdown("#### 结果摘要")
    _render_period_dates(accessor)
    _render_basic_info(accessor)
    _render_error_row(accessor, "MAE")
    _render_error_row(accessor, "RMSE")


__all__ = ["render_all_metrics"]
