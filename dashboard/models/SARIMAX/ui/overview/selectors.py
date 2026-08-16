"""数据概览的选择器与视图开关控件。"""

from __future__ import annotations

import streamlit as st

from dashboard.core.ui.utils.shared_dataset import select_shared_dataset_sheet


def render_variable_selector(st_obj, variables: list[str]) -> list[str]:
    """变量筛选器（同时控制左侧数据表与右侧时间序列图）。"""
    return st_obj.multiselect(
        "选择变量",
        options=variables,
        default=[variables[0]],
        key="sarimax_preview_vars",
        help="选择一个或多个变量；数据表只显示选中列，时间序列图绘制选中序列。",
    )


def _exclusive_view_callback(current_key: str):
    """互斥视图开关：勾选其中一个时取消另一个（head/tail）。"""

    def _callback() -> None:
        for key in (
            "sarimax_table_view_head",
            "sarimax_table_view_tail",
        ):
            if key != current_key:
                st.session_state[key] = False

    return _callback


def render_view_toggles(st_obj) -> None:
    """预览表下方的视图开关（头10行 / 尾10行，互斥并排）。

    默认值经 session_state 预置，避免 checkbox 的 value 参数与
    互斥回调写入冲突。
    """
    for key, default in (
        ("sarimax_table_view_head", True),
        ("sarimax_table_view_tail", False),
    ):
        if key not in st.session_state:
            st.session_state[key] = default
    toggle_row = st_obj.columns(2)
    toggle_row[0].checkbox(
        "显示头10行",
        key="sarimax_table_view_head",
        on_change=_exclusive_view_callback("sarimax_table_view_head"),
        help="预览表显示筛选结果的前 10 行；取消勾选则显示全部。",
    )
    toggle_row[1].checkbox(
        "显示尾10行",
        key="sarimax_table_view_tail",
        on_change=_exclusive_view_callback("sarimax_table_view_tail"),
        help="预览表显示筛选结果的最后 10 行。",
    )


def on_sheet_change() -> None:
    """工作表切换回调：重载对应 sheet 的共享数据。"""
    sheet = st.session_state.get("sarimax_preview_sheet")
    if sheet:
        select_shared_dataset_sheet(sheet)


__all__ = [
    "on_sheet_change",
    "render_variable_selector",
    "render_view_toggles",
]
