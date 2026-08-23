"""数据概览的选择器与视图开关控件。"""

from __future__ import annotations

import streamlit as st

from .widget_keys import preview_key, table_key


def render_variable_selector(
    st_obj, variables: list[str], *, key_prefix: str = "sarimax"
) -> list[str]:
    """变量筛选器（同时控制左侧数据表与右侧时间序列图）。"""
    key = preview_key(key_prefix, "vars")
    if key not in st.session_state:
        st.session_state[key] = [variables[0]]
    else:
        valid = [value for value in st.session_state[key] if value in variables]
        st.session_state[key] = valid or [variables[0]]
    return st_obj.multiselect(
        "选择变量",
        options=variables,
        key=key,
        help="选择一个或多个变量；数据表只显示选中列，时间序列图绘制选中序列。",
    )


def render_view_toggles(st_obj, *, key_prefix: str = "sarimax") -> None:
    """渲染预览表行数选项。"""
    mode_key = table_key(key_prefix, "view_mode")
    rows_key = table_key(key_prefix, "view_rows")
    st_obj.selectbox(
        "显示行数",
        options=("显示头10行", "显示尾10行", "显示指定行数", "显示全部"),
        key=mode_key,
        help="选择预览表显示头部、尾部、指定数量或全部筛选结果。",
    )
    if st.session_state.get(mode_key) == "显示指定行数":
        st_obj.number_input(
            "显示行数",
            min_value=1,
            value=10,
            step=1,
            key=rows_key,
            help="输入要显示的前 N 行观测；超过筛选结果行数时显示全部结果。",
        )


__all__ = [
    "render_variable_selector",
    "render_view_toggles",
]
