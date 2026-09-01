"""SARIMAX 模型页面渲染入口（由内容路由组装标签页）。"""

from dashboard.models.SARIMAX.ui.pages.sarimax_page import (
    render_ardl_model_page,
    render_rdl_model_page,
    render_sarimax_model_page,
)
from dashboard.models.SARIMAX.ui.standalone_model import (
    is_standalone_sarimax_model_request,
    render_standalone_sarimax_model,
)

__all__ = [
    "is_standalone_sarimax_model_request",
    "render_ardl_model_page",
    "render_rdl_model_page",
    "render_sarimax_model_page",
    "render_standalone_sarimax_model",
]
