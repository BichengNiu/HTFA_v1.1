"""HTFA Streamlit 应用入口。"""

from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="经济运行分析平台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.auth.config import AuthConfig
from dashboard.auth.ui.middleware import get_auth_middleware
from dashboard.core.ui.components.content_router import render_main_content
from dashboard.core.ui.components.sidebar import render_complete_sidebar
from dashboard.core.ui.utils.style_loader import inject_cached_styles
from dashboard.navigation_config import MODULE_CONFIG as NAV_MODULE_CONFIG


# 保留入口级名称，方便部署检查和导航回归测试；数据只定义在 navigation_config。
MODULE_CONFIG = NAV_MODULE_CONFIG


def _authenticate():
    """按显式环境配置认证当前用户。"""

    debug_mode = AuthConfig.is_debug_mode()
    middleware = get_auth_middleware()
    current_user = None if debug_mode else middleware.require_authentication(
        show_login=True
    )
    return middleware, current_user, debug_mode


def _set_authorization_state(middleware, current_user, debug_mode: bool) -> None:
    """将侧边栏和内容路由所需的最小权限状态写入会话。"""

    if debug_mode:
        accessible_modules = set(MODULE_CONFIG)
    elif current_user is None:
        accessible_modules = set()
    else:
        accessible_modules = set(
            middleware.permission_manager.get_accessible_modules(current_user)
        )

    st.session_state["auth.debug_mode"] = debug_mode
    st.session_state["auth.current_user"] = current_user
    st.session_state["auth.user_accessible_modules"] = accessible_modules


def _render_user_panel(middleware, current_user) -> None:
    if current_user is None:
        return

    from dashboard.auth.ui.components.user_info_panel import render_user_info_panel

    def handle_logout() -> None:
        middleware.logout()
        st.rerun()

    render_user_info_panel(current_user, on_logout_callback=handle_logout)


def main() -> None:
    """认证、渲染侧边栏并路由主内容。"""

    inject_cached_styles()
    middleware, current_user, debug_mode = _authenticate()
    _set_authorization_state(middleware, current_user, debug_mode)
    _render_user_panel(middleware, current_user)

    render_complete_sidebar(MODULE_CONFIG, key_prefix="sidebar")
    render_main_content()


main()
