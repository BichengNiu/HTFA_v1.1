"""主内容区域的导航与页面分派。"""

from __future__ import annotations

import logging
from collections.abc import Callable

import streamlit as st

from dashboard.core import get_current_main_module, get_current_sub_module
from dashboard.explore.ui.bivariate_page import render_bivariate_analysis_page
from dashboard.explore.ui.pages import render_data_exploration_welcome_page
from dashboard.explore.ui.univariate_page import render_univariate_analysis_page

logger = logging.getLogger(__name__)

PREVIEW_MODULE_MAPPING = {
    "工业": "industrial",
    "阿联酋": "uae",
}


def render_main_content() -> None:
    """根据当前导航状态直接渲染主内容。"""
    main_module = get_current_main_module()
    sub_module = get_current_sub_module()

    if not main_module:
        render_welcome_page()
        return

    try:
        navigation_level = detect_navigation_level(main_module, sub_module)
        if navigation_level == "MAIN_MODULE_ONLY":
            if main_module == "数据探索":
                render_data_exploration_welcome_page(st)
            else:
                render_module_selection_guide(main_module)
            return

        if navigation_level == "SUB_MODULE_ONLY":
            if main_module == "数据探索":
                render_data_exploration_content(sub_module)
            elif main_module == "模型分析":
                render_model_analysis_content(sub_module)
            return

        renderers: dict[str, Callable[[str | None], None]] = {
            "数据预览": render_data_preview_content,
            "监测分析": render_monitoring_analysis_content,
            "模型分析": render_model_analysis_content,
            "数据探索": render_data_exploration_content,
        }
        renderer = renderers.get(main_module)
        if renderer is None:
            st.warning(f"未知的主模块: {main_module}")
            return
        renderer(sub_module)
    except Exception as exc:
        st.error(f"内容渲染失败: {exc}")
        logger.exception("渲染%s失败", main_module)


def detect_navigation_level(main_module: str, sub_module: str | None) -> str:
    """返回当前导航层级。"""
    if not sub_module:
        return "MAIN_MODULE_ONLY"
    if main_module == "数据预览" and sub_module in PREVIEW_MODULE_MAPPING:
        return "FUNCTION_ACTIVE"
    if main_module == "监测分析" and sub_module in {"工业", "阿联酋"}:
        return "FUNCTION_ACTIVE"
    return "SUB_MODULE_ONLY"


def render_data_preview_content(sub_module: str | None) -> None:
    """渲染选中的数据预览领域。"""
    from dashboard.preview.modules import create_preview_renderer

    module_id = PREVIEW_MODULE_MAPPING.get(sub_module or "")
    if module_id is None:
        if sub_module:
            st.error(f"未知的数据预览子模块: {sub_module}")
        else:
            st.info("请在左侧选择一个数据预览子模块")
        return
    create_preview_renderer(module_id).render()


def render_monitoring_analysis_content(sub_module: str | None) -> None:
    """渲染选中的监测分析领域。"""
    if sub_module == "工业":
        from dashboard.analysis.industrial import render_industrial_analysis

        render_industrial_analysis(st)
    elif sub_module == "阿联酋":
        from dashboard.analysis.uae import render_uae_monitoring

        render_uae_monitoring(st)
    else:
        st.info("请选择一个子模块以开始监测分析")


def render_model_analysis_content(sub_module: str | None) -> None:
    """渲染模型分析子模块标签页。"""
    if sub_module == "DFM 模型":
        from dashboard.models.DFM.decomp.ui.pages import render_dfm_news_analysis_page
        from dashboard.models.DFM.prep.ui.pages import render_dfm_data_prep_page
        from dashboard.models.DFM.results.ui.pages import render_dfm_model_analysis_page
        from dashboard.models.DFM.train.ui.pages import render_dfm_model_training_page

        all_tabs = [
            ("数据准备", lambda: render_dfm_data_prep_page(st)),
            ("模型训练", lambda: render_dfm_model_training_page(st)),
            ("模型分析", lambda: render_dfm_model_analysis_page(st)),
            ("影响分解", lambda: render_dfm_news_analysis_page(st)),
        ]
        _render_model_submodule_tabs("DFM 模型", all_tabs)
        return

    if sub_module == "单变量模型":
        from dashboard.models.SARIMAX.ui.pages import render_sarimax_model_page

        all_tabs = [
            ("动态回归模型", lambda: render_sarimax_model_page(st)),
        ]
        _render_model_submodule_tabs("单变量模型", all_tabs)
        return

    st.info("请选择一个模型分析子模块以开始分析")


def _render_model_submodule_tabs(
    sub_module_name: str,
    all_tabs: list[tuple[str, Callable[[], None]]],
) -> None:
    """渲染模型分析子模块下的标签页。"""
    for tab, (tab_name, render_func) in zip(
        st.tabs([name for name, _ in all_tabs]), all_tabs
    ):
        with tab:
            render_func()


def render_data_exploration_content(sub_module: str | None) -> None:
    """渲染数据探索页面。"""
    if sub_module == "单变量分析":
        render_univariate_analysis_page()
    elif sub_module == "多变量分析":
        render_bivariate_analysis_page()
    else:
        st.warning(f"未知的数据探索子模块: {sub_module}")


def render_module_selection_guide(main_module: str) -> None:
    """在尚未选定下一级导航时显示简洁引导。"""
    st.markdown(
        f"""
        <div style="display:flex; flex-direction:column; align-items:center;
                    justify-content:center; height:60vh; text-align:center;">
            <h1 style="font-size:3em; margin-bottom:1rem;">欢迎使用{main_module}</h1>
            <hr style="width:50%; border:1px solid #ccc; margin-top:1rem;">
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_welcome_page() -> None:
    """渲染平台首页。"""
    st.markdown(
        """
        <div style="display:flex; flex-direction:column; align-items:center;
                    justify-content:center; min-height:60vh; text-align:center;">
            <h1 style="font-size:5em; margin:0;">经世</h1>
            <hr style="width:60%; border:0; border-top:1px solid #ccc;
                       margin:1.25rem auto;">
            <p style="font-size:1.8rem; margin:0;">
                国家信息中心经济预测部政策仿真实验室
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


__all__ = ["PREVIEW_MODULE_MAPPING", "detect_navigation_level", "render_main_content"]
