"""应用侧边栏渲染。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from dashboard.core import (
    get_current_main_module,
    get_current_sub_module,
    set_current_main_module,
    set_current_sub_module,
)
from dashboard.core.ui.components.module_selector import (
    render_main_module_selector,
    render_sub_module_selector,
)
from dashboard.core.ui.utils.shared_dataset import render_shared_dataset_uploader


def render_complete_sidebar(
    module_config: Mapping[str, Any],
    key_prefix: str = "sidebar",
) -> None:
    """渲染权限过滤后的导航和共享数据上传器。"""

    if not module_config:
        st.sidebar.error("模块配置为空")
        return

    with st.sidebar:
        debug_mode = st.session_state.get("auth.debug_mode", False)
        current_user = st.session_state.get("auth.current_user")
        permission_manager = None

        if debug_mode:
            st.warning("调试模式：认证和权限检查已禁用")
            st.markdown("")
            main_options = list(module_config)
        elif current_user is None:
            main_options = []
        else:
            from dashboard.auth.ui.middleware import get_auth_middleware

            permission_manager = get_auth_middleware().permission_manager
            main_options = [
                name
                for name in module_config
                if permission_manager.can_access_application_module(current_user, name)
            ]

        st.markdown("### 主模块")
        current_main = get_current_main_module()
        if current_main is not None and current_main not in main_options:
            current_main = main_options[0] if main_options else None
            set_current_main_module(current_main)
        selected_main = render_main_module_selector(
            main_options, current_main, f"{key_prefix}_main"
        )

        st.markdown("---")
        st.markdown("### 子模块")
        if selected_main and isinstance(module_config.get(selected_main), Mapping):
            st.caption(f"当前主模块：{selected_main}")
            sub_options = list(module_config[selected_main])
            if permission_manager is not None:
                allowed = permission_manager.get_accessible_submodules(
                    current_user, selected_main
                )
                sub_options = [name for name in sub_options if name in allowed]

            current_sub = get_current_sub_module()
            if current_sub is not None and current_sub not in sub_options:
                current_sub = None
                set_current_sub_module(None)
            render_sub_module_selector(
                sub_options,
                current_sub,
                selected_main,
                f"{key_prefix}_sub",
            )
        elif not selected_main:
            st.info("请先选择一个主模块")

        st.markdown("---")
        if selected_main in {"数据预览", "监测分析", "数据探索"}:
            render_shared_dataset_uploader(st)
        # 模型分析 - 单变量模型的上传组件已移至页面主区域
        # （与变量选择并排），不再在侧边栏渲染。


__all__ = ["render_complete_sidebar"]
