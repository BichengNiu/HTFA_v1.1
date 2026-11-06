"""SARIMAX 模型页面渲染入口（由内容路由组装标签页）。"""

from htfa.models.univariate.sarimax.ui.pages.sarimax_page import (
    render_ardl_model_page,
    render_rdl_model_page,
    render_sarimax_model_page,
)

__all__ = [
    "render_ardl_model_page",
    "render_rdl_model_page",
    "render_sarimax_model_page",
]
