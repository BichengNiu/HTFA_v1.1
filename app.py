"""HTFA Streamlit 应用入口。"""

from __future__ import annotations

import os
import sys

# 独立组件容器：components/ 下的包（如 data_overview）以顶层名导入，
# 与拷贝到其他项目后的导入方式一致（包内一律相对导入）。
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "components")
)

import streamlit as st


st.set_page_config(
    page_title="经世",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from htfa.app.ui.components.content_router import render_main_content
from htfa.app.ui.components.sidebar import render_complete_sidebar
from htfa.app.ui.style_loader import inject_cached_styles
from dashboard.explore.ui.standalone_data_overview import (
    is_standalone_data_overview_request,
    render_standalone_data_overview,
)
from dashboard.navigation_config import MODULE_CONFIG as NAV_MODULE_CONFIG


# 保留入口级名称，方便部署检查和导航回归测试；数据只定义在 navigation_config。
MODULE_CONFIG = NAV_MODULE_CONFIG


def main() -> None:
    """渲染侧边栏并路由主内容。"""

    inject_cached_styles()
    if st.query_params.get("view") == "sarimax-model":
        from dashboard.models.SARIMAX.ui.standalone_model import (
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
