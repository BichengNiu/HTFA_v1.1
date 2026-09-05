"""Streamlit 主模块与子模块导航状态。"""

from __future__ import annotations

import streamlit as st

from htfa.workspace import SessionWorkspace


MAIN_MODULE_KEY = "navigation.main_module"
SUB_MODULE_KEY = "navigation.sub_module"


def get_current_main_module() -> str | None:
    """返回当前主模块。"""

    return st.session_state.get(MAIN_MODULE_KEY)


def get_current_sub_module() -> str | None:
    """返回当前子模块。"""

    return st.session_state.get(SUB_MODULE_KEY)


def set_current_main_module(module_name: str | None) -> None:
    """更新主模块；主模块改变时清空子模块。"""

    if get_current_main_module() == module_name:
        return
    SessionWorkspace(st.session_state).snapshot_active_page()
    st.session_state[MAIN_MODULE_KEY] = module_name
    st.session_state[SUB_MODULE_KEY] = None


def set_current_sub_module(sub_module_name: str | None) -> None:
    """更新当前子模块。"""

    if get_current_sub_module() == sub_module_name:
        return
    SessionWorkspace(st.session_state).snapshot_active_page()
    st.session_state[SUB_MODULE_KEY] = sub_module_name
