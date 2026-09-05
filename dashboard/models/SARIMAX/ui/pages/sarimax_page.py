"""SARIMAX、RDL 与 ARDL 的独立工作流页面入口。"""

from __future__ import annotations

from htfa.workspace import SessionWorkspace
from dashboard.models.common.model_library import ModelContext
from dashboard.models.common.ui.model_library import render_model_library_save_control
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
        model_context = render_training_section(st_obj, scope)
        st_obj.markdown("---")
        render_analysis_section(st_obj, scope)
        st_obj.markdown("---")
        render_forecast_section(st_obj, scope)
        st_obj.markdown("---")
        _render_save_results_section(
            st_obj,
            scope,
            model_context,
            show_standalone_launcher=show_standalone_launcher,
        )
    finally:
        workspace.end_page(scope.namespace)


def _render_save_results_section(
    st_obj,
    scope: ModelPageScope,
    model_context: ModelContext | None,
    *,
    show_standalone_launcher: bool,
) -> None:
    """在预测结果之后并排提供模型库保存和独立页入口。"""

    st_obj.markdown("**保存结果**")
    columns = st_obj.columns(2 if show_standalone_launcher else 1)
    with columns[0]:
        with st_obj.container(border=True):
            st_obj.markdown("#### 保存到模型库")
            st_obj.caption("保存当前拟合模型的副本，供后续模型性能比较使用。")
            result = scope.state.get("fitted_result")
            signature = scope.state.get("fit_signature")
            if model_context is None or result is None or not signature:
                st_obj.info("完成模型训练后即可加入模型库。")
            else:
                render_model_library_save_control(
                    st_obj,
                    result,
                    family=scope.family,
                    signature=signature,
                    context=model_context,
                )

    if not show_standalone_launcher:
        return
    with columns[1]:
        with st_obj.container(border=True):
            st_obj.markdown("#### 暂存到独立标签页")
            st_obj.caption(
                "复制当前文件、输入和结果到临时页面；之后的修改不会回写本页。"
            )
            url = create_standalone_sarimax_model_url(st_obj)
            if url is None:
                st_obj.info("请先上传并读取 SARIMAX 数据文件。")
                return
            st_obj.link_button(
                "在新标签页打开动态回归模型",
                url,
                icon=":material/open_in_new:",
                width="stretch",
            )


__all__ = [
    "render_ardl_model_page", "render_rdl_model_page", "render_sarimax_model_page",
]
