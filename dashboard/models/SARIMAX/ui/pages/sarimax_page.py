"""SARIMAX 模型 - 单页四环节工作流入口。

环节顺序：① 数据概览 → ② 模型训练 → ③ 模型分析 → ④ 模型预测，
各环节之间以分割线分隔；未满足前置条件的环节显示引导提示。
数据文件在左侧边栏上传（共享数据集）。
"""

from __future__ import annotations

import streamlit as st

from dashboard.models.SARIMAX.ui.pages.sections import (
    render_analysis_section,
    render_data_overview_section,
    render_forecast_section,
    render_training_section,
)


def render_sarimax_model_page(st_obj) -> None:
    """按顺序渲染四环节工作流，环节间以分割线分隔。"""
    render_data_overview_section(st_obj)
    st_obj.markdown("---")
    render_training_section(st_obj)
    st_obj.markdown("---")
    render_analysis_section(st_obj)
    st_obj.markdown("---")
    render_forecast_section(st_obj)


__all__ = ["render_sarimax_model_page"]
