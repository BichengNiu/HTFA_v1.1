"""数据概览的选择器与视图开关控件。"""

from __future__ import annotations

import streamlit as st

from .widget_keys import preview_key


def render_variable_selector(
    st_obj, variables: list[str], *, key_prefix: str = "sarimax"
) -> list[str]:
    """变量筛选器（同时控制左侧数据表与右侧时间序列图）。"""
    return st_obj.multiselect(
        "选择变量",
        options=variables,
        default=[variables[0]],
        key=preview_key(key_prefix, "vars"),
        help="选择一个或多个变量；数据表只显示选中列，时间序列图绘制选中序列。",
    )


def _exclusive_view_callback(key_prefix: str, current_key: str):
    """互斥视图开关：勾选其中一个时取消另一个（head/tail）。"""

    def _callback() -> None:
        for name in ("view_head", "view_tail"):
            key = f"{key_prefix}_table_{name}"
            if key != current_key:
                st.session_state[key] = False

    return _callback


def render_view_toggles(st_obj, *, key_prefix: str = "sarimax") -> None:
    """预览表下方的视图开关（头10行 / 尾10行，互斥并排）。

    默认值经 session_state 预置，避免 checkbox 的 value 参数与
    互斥回调写入冲突。
    """
    head_key = f"{key_prefix}_table_view_head"
    tail_key = f"{key_prefix}_table_view_tail"
    for key, default in (
        (head_key, True),
        (tail_key, False),
    ):
        if key not in st.session_state:
            st.session_state[key] = default
    toggle_row = st_obj.columns(2)
    toggle_row[0].checkbox(
        "显示头10行",
        key=head_key,
        on_change=_exclusive_view_callback(key_prefix, head_key),
        help="预览表显示筛选结果的前 10 行；取消勾选则显示全部。",
    )
    toggle_row[1].checkbox(
        "显示尾10行",
        key=tail_key,
        on_change=_exclusive_view_callback(key_prefix, tail_key),
        help="预览表显示筛选结果的最后 10 行。",
    )


__all__ = [
    "render_variable_selector",
    "render_view_toggles",
]
