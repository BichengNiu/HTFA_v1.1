"""HTFA Streamlit 应用入口。"""

from __future__ import annotations

import streamlit as st

from htfa.ui_shared.fonts import configure_matplotlib_fonts


st.set_page_config(
    page_title="金轩监测",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Must run before HTFA imports any chart module so TsPlots also sees the
# platform font selected for Streamlit Cloud.
configure_matplotlib_fonts()

from htfa.app.ui.components.content_router import render_main_content
from htfa.app.ui.components.sidebar import render_complete_sidebar
from htfa.app.ui.style_loader import inject_cached_styles
from htfa.exploration.ui.standalone_data_overview import (
    is_standalone_data_overview_request,
    render_standalone_data_overview,
)
from htfa.app.navigation.config import MODULE_CONFIG as NAV_MODULE_CONFIG


# 保留入口级名称，方便部署检查和导航回归测试；数据只定义在 app.navigation.config。
MODULE_CONFIG = NAV_MODULE_CONFIG


def main() -> None:
    """渲染侧边栏并路由主内容。"""

    inject_cached_styles()
    if st.query_params.get("view") == "sarimax-model":
        from htfa.models.univariate.sarimax.ui.standalone_model import (
            render_standalone_sarimax_model,
        )

        render_standalone_sarimax_model()
        return
    if is_standalone_data_overview_request():
        render_standalone_data_overview()
        return

    render_complete_sidebar(MODULE_CONFIG, key_prefix="sidebar")
    render_main_content()


main()
