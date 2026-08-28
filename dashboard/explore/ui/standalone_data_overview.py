"""新标签页中的单变量数据概览入口。"""

from __future__ import annotations

import json
from hashlib import sha256
from urllib.parse import urlencode

import streamlit as st

from dashboard.core.ui.utils.shared_dataset import (
    export_shared_dataset_snapshot,
    restore_shared_dataset_snapshot,
)
from dashboard.core.workspace import SessionWorkspace
from dashboard.explore.core.overview_handoff import (
    OverviewHandoff,
    overview_handoff_store,
)
from dashboard.explore.ui.data_overview import (
    CORRELOGRAM_TRANSFORMATION_PREFIX,
    DATA_OVERVIEW_HANDOFF_WIDGET_KEYS,
    SERIES_STYLE_WIDGET_PREFIX,
    export_data_overview_widget_state,
    mark_data_overview_handoff_restore,
    render_data_overview,
    restore_data_overview_widget_state,
)

STANDALONE_VIEW = "univariate-overview"
HANDOFF_QUERY_KEY = "handoff"
_HANDOFF_TOKEN_STATE_KEY = "exploration.standalone_overview.handoff_token"
_HANDOFF_SIGNATURE_STATE_KEY = "exploration.standalone_overview.handoff_signature"
_PAGE_ID = "exploration.univariate.overview_standalone"
_PERSISTENT_PREFIXES = (
    "tools.analysis.chart_config.",
    CORRELOGRAM_TRANSFORMATION_PREFIX,
    SERIES_STYLE_WIDGET_PREFIX,
)


def is_standalone_data_overview_request() -> bool:
    """当前 URL 是否请求独立数据概览页。"""

    return st.query_params.get("view") == STANDALONE_VIEW


def create_standalone_data_overview_url(st_obj) -> str | None:
    """为当前共享数据与概览设置创建新标签页 URL。"""

    dataset = export_shared_dataset_snapshot()
    if dataset is None:
        return None
    handoff = OverviewHandoff(
        dataset=dataset,
        widget_state=export_data_overview_widget_state(st_obj),
    )
    signature = _handoff_signature(handoff)
    previous_token = st_obj.session_state.get(_HANDOFF_TOKEN_STATE_KEY)
    previous_signature = st_obj.session_state.get(_HANDOFF_SIGNATURE_STATE_KEY)
    if (
        previous_token
        and previous_signature == signature
        and overview_handoff_store.is_valid(previous_token)
    ):
        token = previous_token
    else:
        token = overview_handoff_store.replace(previous_token, handoff)
        st_obj.session_state[_HANDOFF_TOKEN_STATE_KEY] = token
        st_obj.session_state[_HANDOFF_SIGNATURE_STATE_KEY] = signature
    return "?" + urlencode({"view": STANDALONE_VIEW, HANDOFF_QUERY_KEY: token})


def _handoff_signature(handoff: OverviewHandoff) -> str:
    """为文件和控件快照生成稳定签名，避免无关重跑替换令牌。"""

    payload = json.dumps(
        {
            "fingerprint": handoff.dataset.asset.fingerprint,
            "file_name": handoff.dataset.asset.name,
            "sheet": handoff.dataset.sheet,
            "widget_state": handoff.widget_state,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=repr,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def render_standalone_data_overview() -> None:
    """恢复交接快照后，渲染不含主导航的独立数据概览页。"""

    token = st.query_params.get(HANDOFF_QUERY_KEY)
    restored_token = st.session_state.get(_HANDOFF_TOKEN_STATE_KEY)
    if token and token != restored_token:
        handoff = overview_handoff_store.get(token)
        if handoff is None:
            _render_handoff_error()
            return
        try:
            restore_shared_dataset_snapshot(handoff.dataset, allow_unparsed=True)
            restore_data_overview_widget_state(st, handoff.widget_state)
            mark_data_overview_handoff_restore(st)
        except Exception as exc:  # noqa: BLE001 - 页面交接的用户提示边界
            st.error(f"数据概览交接失败：{exc}")
            return
        st.session_state[_HANDOFF_TOKEN_STATE_KEY] = token
        st.query_params.pop(HANDOFF_QUERY_KEY, None)
        st.query_params["view"] = STANDALONE_VIEW
        st.rerun()

    if not restored_token:
        _render_handoff_error()
        return

    workspace = SessionWorkspace(st.session_state)
    workspace.begin_page(
        _PAGE_ID,
        keys=DATA_OVERVIEW_HANDOFF_WIDGET_KEYS,
        prefixes=_PERSISTENT_PREFIXES,
    )
    try:
        st.title("数据概览")
        st.caption("此页面是独立查看窗口，设置修改不会回写原单变量分析页。")
        render_data_overview(st)
    finally:
        workspace.end_page(_PAGE_ID)


def _render_handoff_error() -> None:
    st.error("数据概览链接已失效或服务已重启，请返回原页面后重新打开。")


__all__ = [
    "HANDOFF_QUERY_KEY",
    "STANDALONE_VIEW",
    "create_standalone_data_overview_url",
    "is_standalone_data_overview_request",
    "render_standalone_data_overview",
]
