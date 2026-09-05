"""独立动态回归模型页的短期交接与渲染入口。"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

from htfa.workspace import DatasetSnapshot, HandoffStore
from htfa.models.univariate.common.model_library import (
    MODEL_LIBRARY_TOKEN_KEY,
    model_library_store,
)
from htfa.models.univariate.common.ui.model_library import render_model_library_sidebar
from htfa.models.univariate.sarimax.ui.data_input import (
    SARIMAX_DATA_OVERVIEW_WIDGET_KEYS,
    export_sarimax_data_snapshot,
    mark_sarimax_handoff_restore,
)
from htfa.models.univariate.sarimax.ui.state import (
    PERSISTENT_WIDGET_KEYS,
    RESULT_KEYS,
    clear_fit_results,
    clear_widget_state,
    restore_result_state,
    state,
)


STANDALONE_VIEW = "sarimax-model"
HANDOFF_QUERY_KEY = "handoff"
_HANDOFF_TOKEN_STATE_KEY = "model_analysis.sarimax.standalone.handoff_token"
_HANDOFF_SIGNATURE_STATE_KEY = (
    "model_analysis.sarimax.standalone.handoff_signature"
)
_HANDOFF_RESTORE_STATE_KEY = "model_analysis.sarimax.standalone.restored"
_HANDOFF_PREFIXES = (
    "sarimax_future_exog_source_",
    "sarimax_exog_log_",
)
_HANDOFF_RESULT_KEYS = RESULT_KEYS + ("forecast_widget_fit_signature",)

SARIMAX_HANDOFF_WIDGET_KEYS = tuple(
    dict.fromkeys(
        key
        for key in SARIMAX_DATA_OVERVIEW_WIDGET_KEYS + PERSISTENT_WIDGET_KEYS
    )
)


@dataclass(frozen=True)
class SARIMAXHandoff:
    """独立动态回归模型页所需的输入与结果上下文快照。"""

    dataset: DatasetSnapshot
    widget_state: dict[str, object]
    result_state: dict[str, object]
    model_library_token: str


sarimax_handoff_store: HandoffStore[SARIMAXHandoff] = HandoffStore()


def is_standalone_sarimax_model_request() -> bool:
    """当前 URL 是否请求独立动态回归模型页。"""

    return st.query_params.get("view") == STANDALONE_VIEW


def export_sarimax_widget_state(st_obj) -> dict[str, object]:
    """导出按钮和下载控件之外的 SARIMAX 可编辑输入状态。"""

    widget_state = {
        key: deepcopy(st_obj.session_state[key])
        for key in SARIMAX_HANDOFF_WIDGET_KEYS
        if key in st_obj.session_state
    }
    widget_state.update(
        {
            str(key): deepcopy(st_obj.session_state[key])
            for key in st_obj.session_state
            if str(key).startswith(_HANDOFF_PREFIXES)
        }
    )
    return widget_state


def export_sarimax_result_state() -> dict[str, object]:
    """导出拟合、诊断和预测缓存，并为每个交接页创建独立副本。"""
    result_state = {
        key: deepcopy(state.get(key))
        for key in _HANDOFF_RESULT_KEYS
    }
    result_state["fit_config"] = deepcopy(state.get("fit_config"))
    return result_state


def restore_sarimax_widget_state(st_obj, widget_state: dict[str, object]) -> None:
    """恢复已校验的 SARIMAX 可编辑输入状态。"""

    allowed = set(SARIMAX_HANDOFF_WIDGET_KEYS)
    for key, value in widget_state.items():
        if key in allowed or key.startswith(_HANDOFF_PREFIXES):
            st_obj.session_state[key] = deepcopy(value)


def restore_sarimax_result_state(result_state: dict[str, object]) -> None:
    """恢复交接的模型结果缓存，避免与来源页面共享可变对象。"""

    restore_result_state(result_state, keys=_HANDOFF_RESULT_KEYS)
    state.set("fit_config", deepcopy(result_state.get("fit_config")))


def create_standalone_sarimax_model_url(st_obj) -> str | None:
    """为当前 SARIMAX 文件与输入设置创建独立页面 URL。"""

    dataset = export_sarimax_data_snapshot()
    if dataset is None:
        return None
    model_library_token = st_obj.session_state.get(MODEL_LIBRARY_TOKEN_KEY)
    if (
        not isinstance(model_library_token, str)
        or model_library_store.get(model_library_token) is None
    ):
        model_library_token = model_library_store.create()
        st_obj.session_state[MODEL_LIBRARY_TOKEN_KEY] = model_library_token
    handoff = SARIMAXHandoff(
        dataset=dataset,
        widget_state=export_sarimax_widget_state(st_obj),
        result_state=export_sarimax_result_state(),
        model_library_token=model_library_token,
    )
    signature = _handoff_signature(handoff)
    previous_token = st_obj.session_state.get(_HANDOFF_TOKEN_STATE_KEY)
    previous_signature = st_obj.session_state.get(_HANDOFF_SIGNATURE_STATE_KEY)
    if (
        previous_token
        and previous_signature == signature
        and sarimax_handoff_store.is_valid(previous_token)
    ):
        token = previous_token
    else:
        token = sarimax_handoff_store.replace(previous_token, handoff)
        st_obj.session_state[_HANDOFF_TOKEN_STATE_KEY] = token
        st_obj.session_state[_HANDOFF_SIGNATURE_STATE_KEY] = signature
    return "?" + urlencode({"view": STANDALONE_VIEW, HANDOFF_QUERY_KEY: token})


def _handoff_signature(handoff: SARIMAXHandoff) -> str:
    """为文件与输入快照生成稳定签名，避免无关重跑替换令牌。"""

    payload = json.dumps(
        {
            "fingerprint": handoff.dataset.asset.fingerprint,
            "file_name": handoff.dataset.asset.name,
            "sheet": handoff.dataset.sheet,
            "widget_state": handoff.widget_state,
            "result_state": handoff.result_state,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=repr,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def render_standalone_sarimax_model() -> None:
    """恢复交接快照后渲染无主导航的独立动态回归模型页。"""

    token = st.query_params.get(HANDOFF_QUERY_KEY)
    restored_token = st.session_state.get(_HANDOFF_RESTORE_STATE_KEY)
    if token and token != restored_token:
        handoff = sarimax_handoff_store.get(token)
        if handoff is None:
            _render_handoff_error()
            return
        try:
            _clear_previous_model_state()
            restore_sarimax_widget_state(st, handoff.widget_state)
            _seed_sarimax_input_state(handoff.widget_state)
            variable_name_row, data_start_row = _read_handoff_rows(
                handoff.widget_state
            )
            mark_sarimax_handoff_restore(
                st,
                handoff.dataset,
                variable_name_row=variable_name_row,
                data_start_row=data_start_row,
            )
            restore_sarimax_result_state(handoff.result_state)
            if model_library_store.get(handoff.model_library_token) is None:
                raise ValueError("模型库交接标识已失效")
            st.session_state[MODEL_LIBRARY_TOKEN_KEY] = handoff.model_library_token
        except Exception as exc:  # noqa: BLE001 - 页面交接用户提示边界
            st.error(f"动态回归模型交接失败：{exc}")
            return
        st.session_state[_HANDOFF_RESTORE_STATE_KEY] = token
        st.query_params.pop(HANDOFF_QUERY_KEY, None)
        st.query_params["view"] = STANDALONE_VIEW
        st.rerun()

    if not restored_token:
        _render_handoff_error()
        return

    from htfa.models.univariate.sarimax.ui.pages.sarimax_page import (
        render_sarimax_model_page,
    )

    st.title("动态回归模型")
    st.caption("此页面是独立查看窗口，设置修改不会回写原动态回归模型页。")
    with st.sidebar:
        render_model_library_sidebar(st)
    render_sarimax_model_page(st)


def _clear_previous_model_state() -> None:
    """切换交接快照时清空当前独立页的旧输入和派生结果。"""

    clear_fit_results()
    clear_widget_state(st)
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(_HANDOFF_PREFIXES):
            st.session_state.pop(key, None)
    for key, value in (
        ("dataset", None),
        ("source_fingerprint", None),
        ("time_options_signature", None),
        ("target_variable", None),
        ("exog_variables", ()),
        ("exog_log_names", ()),
        ("training_time_range", None),
        ("data_preprocessing", ()),
        ("missing_value_method", "无"),
        ("data_processing_base_fingerprint", None),
        ("data_processing_signature", None),
        ("data_processing_frame", None),
        ("data_processing_auto_start", False),
        ("response_log", False),
        ("model_selection", None),
        ("future_exog_editor_signature", None),
    ):
        state.set(key, value)


def _seed_sarimax_input_state(widget_state: dict[str, object]) -> None:
    """让首次训练渲染识别已恢复的输入及其内部签名。"""

    target = widget_state.get("sarimax_target_select")
    if isinstance(target, str):
        state.set("target_variable", target)
    exog = widget_state.get("sarimax_exog_select", ())
    if isinstance(exog, (list, tuple)):
        state.set("exog_variables", tuple(str(value) for value in exog))
    training_range = widget_state.get("sarimax_train_forecast_window")
    if isinstance(training_range, (list, tuple)) and len(training_range) == 2:
        try:
            state.set(
                "training_time_range",
                tuple(pd.Timestamp(value) for value in training_range),
            )
        except (TypeError, ValueError):
            pass
    preprocessing = widget_state.get("sarimax_data_preprocessing", ())
    if isinstance(preprocessing, (list, tuple)):
        state.set(
            "data_preprocessing",
            tuple(str(value) for value in preprocessing),
        )
    missing_value_method = widget_state.get(
        "sarimax_missing_value_method",
        "无",
    )
    if isinstance(missing_value_method, str):
        state.set("missing_value_method", missing_value_method)
    family = widget_state.get("sarimax_model_family", "SARIMAX")
    mode = widget_state.get("sarimax_config_mode", "手动配置")
    if isinstance(family, str) and isinstance(mode, str):
        state.set("model_selection", (family, mode))
        state.set(
            "response_log",
            bool(widget_state.get("sarimax_response_log", False)),
        )


def _read_handoff_rows(widget_state: dict[str, object]) -> tuple[int, int]:
    """读取交接数据的行设置，非法值交给组件边界重新校正。"""

    try:
        variable_name_row = int(
            widget_state.get("sarimax_model_preview_variable_name_row", 1)
        )
    except (TypeError, ValueError):
        variable_name_row = 1
    try:
        data_start_row = int(
            widget_state.get(
                "sarimax_model_preview_data_start_row",
                variable_name_row + 1,
            )
        )
    except (TypeError, ValueError):
        data_start_row = variable_name_row + 1
    return variable_name_row, data_start_row


def _render_handoff_error() -> None:
    st.error("动态回归模型链接已失效或服务已重启，请返回原页面后重新打开。")


__all__ = [
    "HANDOFF_QUERY_KEY",
    "SARIMAX_HANDOFF_WIDGET_KEYS",
    "SARIMAXHandoff",
    "STANDALONE_VIEW",
    "create_standalone_sarimax_model_url",
    "export_sarimax_widget_state",
    "is_standalone_sarimax_model_request",
    "render_standalone_sarimax_model",
    "restore_sarimax_widget_state",
    "sarimax_handoff_store",
]
