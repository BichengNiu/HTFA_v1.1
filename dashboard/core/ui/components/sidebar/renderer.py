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
    """渲染导航和共享数据上传器。"""

    if not module_config:
        st.sidebar.error("模块配置为空")
        return

    with st.sidebar:
        main_options = list(module_config)

        st.markdown(
            """
            <div style="text-align:center; font-size:2em; font-weight:600;
                        margin:0.5rem 0 0.75rem;">
                经世
            </div>
            <hr style="width:70%; border:0; border-top:1px solid #fff;
                       margin:0 auto 2rem;">
            """,
            unsafe_allow_html=True,
        )
        st.markdown("### 主模块")
        current_main = get_current_main_module()
        if current_main is not None and current_main not in main_options:
            current_main = main_options[0] if main_options else None
            set_current_main_module(current_main)
        selected_main = render_main_module_selector(
            main_options, current_main, f"{key_prefix}_main"
        )

        st.markdown('<hr style="margin:0.5rem 0;">', unsafe_allow_html=True)
        st.markdown("### 子模块")
        if selected_main and isinstance(module_config.get(selected_main), Mapping):
            st.caption(f"当前主模块：{selected_main}")
            sub_options = list(module_config[selected_main])

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
        if selected_main in {"数据探索", "监测分析"}:
            render_shared_dataset_uploader(st)
        # 模型页直接读取数据探索中的共享数据集，不在模型页重复渲染上传器。

        st.markdown(
            """
            <div style="position:fixed; bottom:1rem; left:0.5rem; width:18rem;
                        text-align:center; font-size:0.75rem; line-height:1.4;
                        color:#fff;">
                @版权所有：国家信息中心经济预测部政策仿真实验室 牛碧珵
            </div>
            """,
            unsafe_allow_html=True,
        )


__all__ = ["render_complete_sidebar"]
