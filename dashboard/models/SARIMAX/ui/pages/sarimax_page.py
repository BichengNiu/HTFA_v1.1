"""SARIMAX、RDL 与 ARDL 的独立工作流页面入口。"""

from __future__ import annotations

from dashboard.core.workspace import SessionWorkspace
from dashboard.models.SARIMAX.ui.data_input import (
    get_model_data_input,
    render_model_data_input,
)
from dashboard.models.SARIMAX.ui.pages.sections import (
    render_analysis_section,
    render_forecast_section,
    render_training_section,
)
from dashboard.models.SARIMAX.ui.standalone_model import create_standalone_sarimax_model_url
from dashboard.models.SARIMAX.ui.state import ARDL_SCOPE, ModelPageScope, RDL_SCOPE, SARIMAX_SCOPE


def render_sarimax_model_page(st_obj) -> None:
    """渲染仅包含 SARIMAX 的动态回归模型 Tab。"""
    _render_model_page(st_obj, SARIMAX_SCOPE, show_standalone_launcher=True)


def render_rdl_model_page(st_obj) -> None:
    """渲染独立的 RDL 模型 Tab。"""
    _render_model_page(st_obj, RDL_SCOPE)


def render_ardl_model_page(st_obj) -> None:
    """渲染独立的 ARDL 模型 Tab。"""
    _render_model_page(st_obj, ARDL_SCOPE)


def _render_model_page(
    st_obj,
    scope: ModelPageScope,
    *,
    show_standalone_launcher: bool = False,
) -> None:
    """按模型范围编排读取、训练、诊断与预测。"""
    workspace = SessionWorkspace(st_obj.session_state)
    workspace.begin_page(
        scope.namespace,
        keys=scope.persistent_widget_keys + get_model_data_input(scope).overview_widget_keys,
        prefixes=(
            f"{scope.key_prefix}_future_exog_source_",
            f"{scope.key_prefix}_exog_log_",
        ),
    )
    try:
        render_model_data_input(st_obj, scope)
        st_obj.markdown("---")
        render_training_section(st_obj, scope)
        st_obj.markdown("---")
        render_analysis_section(st_obj, scope)
        st_obj.markdown("---")
        render_forecast_section(st_obj, scope)
        if show_standalone_launcher:
            st_obj.markdown("---")
            _render_standalone_model_launcher(st_obj)
    finally:
        workspace.end_page(scope.namespace)


def _render_standalone_model_launcher(st_obj) -> None:
    """复制 SARIMAX 输入上下文到浏览器独立标签页。"""
    st_obj.markdown("**复制到独立标签页**")
    st_obj.caption("新页面会复制当前文件、读取设置以及当前的拟合、诊断和预测结果；两边之后可分别继续操作。")
    url = create_standalone_sarimax_model_url(st_obj)
    if url is None:
        st_obj.info("请先上传并读取 SARIMAX 数据文件。")
        return
    st_obj.link_button("在新标签页打开动态回归模型", url, icon=":material/open_in_new:")


__all__ = [
    "render_ardl_model_page", "render_rdl_model_page", "render_sarimax_model_page",
]
