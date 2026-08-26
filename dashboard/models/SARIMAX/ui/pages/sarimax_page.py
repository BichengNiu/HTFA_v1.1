"""动态回归模型 - 单页四环节工作流入口。

环节顺序：① 数据预览 → ② 模型训练 → ③ 残差诊断 → ④ 模型预测，
各环节之间以分割线分隔；未满足前置条件的环节显示引导提示。
数据文件在左侧边栏上传（共享数据集）。
"""

from __future__ import annotations

from dashboard.models.SARIMAX.ui.pages.sections import (
    render_analysis_section,
    render_data_overview_section,
    render_forecast_section,
    render_training_section,
)
from dashboard.core.workspace import SessionWorkspace
from dashboard.models.SARIMAX.ui.state import PERSISTENT_WIDGET_KEYS


_PAGE_ID = "model_analysis.sarimax"


def render_sarimax_model_page(st_obj) -> None:
    """按顺序渲染数据、训练、残差诊断和预测四个环节。"""
    workspace = SessionWorkspace(st_obj.session_state)
    workspace.begin_page(_PAGE_ID, keys=PERSISTENT_WIDGET_KEYS)
    try:
        render_data_overview_section(st_obj)
        st_obj.markdown("---")
        render_training_section(st_obj)
        st_obj.markdown("---")
        render_analysis_section(st_obj)
        st_obj.markdown("---")
        render_forecast_section(st_obj)
    finally:
        workspace.end_page(_PAGE_ID)


__all__ = ["render_sarimax_model_page"]
