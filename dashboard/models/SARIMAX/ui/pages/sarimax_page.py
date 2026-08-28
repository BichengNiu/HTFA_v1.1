"""动态回归模型 - 单页三环节工作流入口。

数据预览已统一放在“数据探索 → 单变量分析 → 数据概览”；本页负责模型训练、
残差诊断和模型预测。
"""

from __future__ import annotations

from dashboard.models.SARIMAX.ui.pages.sections import (
    render_analysis_section,
    render_forecast_section,
    render_training_section,
)
from dashboard.core.workspace import SessionWorkspace
from dashboard.models.SARIMAX.ui.state import PERSISTENT_WIDGET_KEYS


_PAGE_ID = "model_analysis.sarimax"


def render_sarimax_model_page(st_obj) -> None:
    """按顺序渲染模型训练、残差诊断和模型预测三个环节。"""
    workspace = SessionWorkspace(st_obj.session_state)
    workspace.begin_page(
        _PAGE_ID,
        keys=PERSISTENT_WIDGET_KEYS,
        prefixes=("sarimax_future_exog_source_",),
    )
    try:
        render_training_section(st_obj)
        st_obj.markdown("---")
        render_analysis_section(st_obj)
        st_obj.markdown("---")
        render_forecast_section(st_obj)
    finally:
        workspace.end_page(_PAGE_ID)


__all__ = ["render_sarimax_model_page"]
