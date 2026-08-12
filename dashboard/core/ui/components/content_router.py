"""主内容区域的导航与页面分派。"""

from __future__ import annotations

import logging
from collections.abc import Callable

import streamlit as st

from dashboard.auth.ui.pages.user_management_module import (
    UserManagementWelcomePage,
    render_user_management_sub_module,
)
from dashboard.core import get_current_main_module, get_current_sub_module
from dashboard.explore.ui.bivariate_page import render_bivariate_analysis_page
from dashboard.explore.ui.pages import render_data_exploration_welcome_page
from dashboard.explore.ui.univariate_page import render_univariate_analysis_page

logger = logging.getLogger(__name__)

PREVIEW_MODULE_MAPPING = {
    "工业": "industrial",
    "阿联酋": "uae",
}


def check_user_permission(module_name: str) -> tuple[bool, str | None]:
    """检查当前用户能否访问应用主模块。"""
    try:
        if st.session_state.get("auth.debug_mode", True):
            return True, None

        current_user = st.session_state.get("auth.current_user")
        if current_user is None:
            return False, f"请先登录后访问「{module_name}」模块"

        from dashboard.auth.ui.middleware import get_auth_middleware

        permission_manager = get_auth_middleware().permission_manager
        if permission_manager.can_access_application_module(current_user, module_name):
            return True, None

        if permission_manager.is_admin(current_user):
            return False, f"管理员账户无法访问「{module_name}」模块，仅可访问用户管理"
        if module_name == "用户管理":
            return False, "只有管理员才能访问「用户管理」模块"
        return False, f"您没有访问「{module_name}」模块的权限，请联系管理员"
    except Exception as exc:
        logger.exception("权限检查失败")
        return False, f"权限检查失败: {exc}"


def render_main_content() -> None:
    """根据当前导航状态直接渲染主内容。"""
    main_module = get_current_main_module()
    sub_module = get_current_sub_module()

    if not main_module:
        render_welcome_page()
        return

    has_permission, _ = check_user_permission(main_module)
    if not has_permission:
        st.error("无访问权限")
        return

    try:
        navigation_level = detect_navigation_level(main_module, sub_module)
        if navigation_level == "MAIN_MODULE_ONLY":
            if main_module == "数据探索":
                render_data_exploration_welcome_page(st)
            else:
                render_module_selection_guide(main_module, "sub_module")
            return

        if navigation_level == "SUB_MODULE_ONLY":
            if main_module == "数据探索":
                render_data_exploration_content(sub_module)
            elif main_module == "模型分析":
                render_model_analysis_content(sub_module)
            else:
                render_module_selection_guide(main_module, "function")
            return

        renderers: dict[str, Callable[[str | None], None]] = {
            "数据预览": render_data_preview_content,
            "监测分析": render_monitoring_analysis_content,
            "模型分析": render_model_analysis_content,
            "数据探索": render_data_exploration_content,
            "用户管理": render_user_management_content,
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
    if main_module == "用户管理":
        return "FUNCTION_ACTIVE"
    if not sub_module:
        return "MAIN_MODULE_ONLY"
    if main_module == "数据预览" and sub_module in PREVIEW_MODULE_MAPPING:
        return "FUNCTION_ACTIVE"
    if main_module == "监测分析" and sub_module in {"工业", "阿联酋"}:
        return "FUNCTION_ACTIVE"
    return "SUB_MODULE_ONLY"


def render_data_preview_content(sub_module: str | None) -> None:
    """渲染选中的数据预览领域。"""
    from dashboard.preview.modules import PreviewModuleRegistry

    module_id = PREVIEW_MODULE_MAPPING.get(sub_module or "")
    if module_id is None:
        if sub_module:
            st.error(f"未知的数据预览子模块: {sub_module}")
        else:
            st.info("请在左侧选择一个数据预览子模块")
        return
    PreviewModuleRegistry.create_renderer(module_id).render()


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
    """渲染 DFM 分析标签页。"""
    if sub_module != "DFM 模型":
        st.info("请选择一个模型分析子模块以开始分析")
        return

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
    current_user = st.session_state.get("auth.current_user")
    if st.session_state.get("auth.debug_mode", False) or current_user is None:
        visible_tabs = all_tabs
    else:
        from dashboard.auth.ui.middleware import get_auth_middleware

        permission_manager = get_auth_middleware().permission_manager
        visible_tabs = [
            (tab_name, render_func)
            for tab_name, render_func in all_tabs
            if permission_manager.check_granular_access(
                current_user, "模型分析", "DFM 模型", tab_name
            )
        ]

    if not visible_tabs:
        st.warning("您没有权限访问任何Tab")
        return

    for tab, (tab_name, render_func) in zip(
        st.tabs([name for name, _ in visible_tabs]), visible_tabs
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


def render_user_management_content(sub_module: str | None) -> None:
    """渲染用户管理主页或子页面。"""
    if sub_module:
        render_user_management_sub_module(sub_module)
    else:
        UserManagementWelcomePage.render()


def render_module_selection_guide(main_module: str, guide_type: str) -> None:
    """在尚未选定下一级导航时显示简洁引导。"""
    if guide_type != "sub_module":
        st.markdown("")
        return
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
        <div class="platform-header">
            <h1 class="platform-title">经济运行分析平台</h1>
            <hr class="platform-divider">
            <p class="platform-subtitle">国家信息中心经济预测部政策仿真实验室</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


__all__ = ["PREVIEW_MODULE_MAPPING", "detect_navigation_level", "render_main_content"]
