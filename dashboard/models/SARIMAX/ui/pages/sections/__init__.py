"""SARIMAX 单页工作流的四环节组件。

① 数据预览由独立组件包 data_overview 提供（components/data_overview/），
此处按 SARIMAX 场景接线：key_prefix/state_namespace 使用 SARIMAX
命名空间，数据源走 HTFA 全局共享数据集，换文件时清理模型训练状态。
"""

from __future__ import annotations

from data_overview import create_data_overview

from dashboard.models.SARIMAX.core.data_loader import build_modeling_dataset
from dashboard.models.SARIMAX.ui.overview_bridge import SharedDatasetSource
from dashboard.models.SARIMAX.ui.pages.sections.analysis_section import (
    render_analysis_section,
)
from dashboard.models.SARIMAX.ui.pages.sections.forecast_section import (
    render_forecast_section,
)
from dashboard.models.SARIMAX.ui.pages.sections.training_section import (
    render_training_section,
)
from dashboard.models.SARIMAX.ui.state import (
    DATASET_REPLACED_WIDGET_KEYS,
    clear_fit_results,
    clear_widget_state,
    state,
)


def _on_sarimax_dataset_replaced(st_obj) -> None:
    """数据预览输入变化后清理 SARIMAX 训练/诊断/预测状态。"""
    state.set("target_variable", None)
    state.set("exog_variables", ())
    state.set("training_time_range", None)
    state.set("response_log", False)
    state.set("future_exog_editor_signature", None)
    clear_fit_results()
    clear_widget_state(st_obj, DATASET_REPLACED_WIDGET_KEYS)
    session = getattr(st_obj, "session_state", None)
    if session is not None:
        for key in tuple(session):
            if str(key).startswith("sarimax_future_exog_source_"):
                session.pop(key, None)


render_data_overview_section = create_data_overview(
    key_prefix="sarimax",
    state_namespace="model_analysis.sarimax",
    data_source=SharedDatasetSource(),
    dataset_builder=build_modeling_dataset,
    on_dataset_replaced=_on_sarimax_dataset_replaced,
    title="#### ① 数据预览",
)

__all__ = [
    "render_analysis_section",
    "render_data_overview_section",
    "render_forecast_section",
    "render_training_section",
]
