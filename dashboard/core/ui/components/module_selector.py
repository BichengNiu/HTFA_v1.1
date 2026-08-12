"""两列式主模块与子模块选择器。"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from dashboard.core import set_current_main_module, set_current_sub_module
from dashboard.core.ui.utils.debug_helpers import debug_button_click


FIRST_COLUMN_MODULES = {"数据预览", "模型分析", "用户管理"}
SECOND_COLUMN_MODULES = {"监测分析", "数据探索"}


def render_main_module_selector(
    module_options: Sequence[str],
    current_module: str | None,
    key_prefix: str = "main_module",
) -> str | None:
    """渲染主模块按钮并返回当前选择。"""

    selected = _render_option_buttons(
        module_options, current_module, key_prefix, "主模块"
    )
    if selected != current_module:
        set_current_main_module(selected)
    return selected


def render_sub_module_selector(
    sub_module_options: Sequence[str],
    current_sub_module: str | None,
    main_module: str,
    key_prefix: str = "sub_module",
) -> str | None:
    """渲染子模块按钮并返回当前选择。"""

    selected = _render_option_buttons(
        sub_module_options,
        current_sub_module,
        key_prefix,
        f"{main_module} 子模块",
    )
    if selected != current_sub_module:
        set_current_sub_module(selected)
    return selected


def _render_option_buttons(
    options: Sequence[str],
    current: str | None,
    key_prefix: str,
    label: str,
) -> str | None:
    if not options:
        return current
    if not all(isinstance(option, str) and option.strip() for option in options):
        raise ValueError("导航选项必须是非空字符串")

    selected = current
    columns = st.columns(2)
    for column_index, column_options in enumerate(_distribute_options(options)):
        with columns[column_index]:
            for option in column_options:
                key = f"{key_prefix}_col{column_index + 1}_{option}"
                if st.button(option, type="secondary", key=key, width="stretch"):
                    debug_button_click(label, f"从 {current} 切换到 {option}")
                    selected = option
    return selected


def _distribute_options(options: Sequence[str]) -> tuple[list[str], list[str]]:
    first: list[str] = []
    second: list[str] = []
    for option in options:
        if option in FIRST_COLUMN_MODULES:
            first.append(option)
        elif option in SECOND_COLUMN_MODULES:
            second.append(option)
        elif len(first) <= len(second):
            first.append(option)
        else:
            second.append(option)
    return first, second


__all__ = ["render_main_module_selector", "render_sub_module_selector"]
