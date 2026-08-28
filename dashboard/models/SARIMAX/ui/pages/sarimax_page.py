"""动态回归模型 - 独立数据读取、训练、诊断和预测工作流入口。"""

from __future__ import annotations

from dashboard.models.SARIMAX.ui.pages.sections import (
    render_analysis_section,
    render_forecast_section,
    render_training_section,
)
from dashboard.models.SARIMAX.ui.data_input import (
    SARIMAX_DATA_OVERVIEW_WIDGET_KEYS,
    render_sarimax_data_input,
)
from dashboard.core.workspace import SessionWorkspace
from dashboard.models.SARIMAX.ui.state import PERSISTENT_WIDGET_KEYS


_PAGE_ID = "model_analysis.sarimax"


def render_sarimax_model_page(st_obj) -> None:
    """按顺序渲染模型训练、残差诊断和模型预测三个环节。"""
    workspace = SessionWorkspace(st_obj.session_state)
    workspace.begin_page(
        _PAGE_ID,
        keys=PERSISTENT_WIDGET_KEYS + SARIMAX_DATA_OVERVIEW_WIDGET_KEYS,
        prefixes=("sarimax_future_exog_source_",),
    )
    try:
        render_sarimax_data_input(st_obj)
        st_obj.markdown("---")
        render_training_section(st_obj)
        st_obj.markdown("---")
        render_analysis_section(st_obj)
        st_obj.markdown("---")
        render_forecast_section(st_obj)
    finally:
        workspace.end_page(_PAGE_ID)


__all__ = ["render_sarimax_model_page"]
