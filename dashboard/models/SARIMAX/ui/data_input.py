"""SARIMAX 自有的数据读取入口，不依赖数据探索页面。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st
from data_overview.core.file_parsing import file_fingerprint
from data_overview.ui.data_source import BuiltinDataSource
from data_overview.ui.widget_keys import overview_widget_keys

from dashboard.core.workspace import FileAsset
from dashboard.models.common.ui.data_input import create_data_input_module
from dashboard.models.SARIMAX.core.data_loader import (
    DATA_REPLACEMENT_OPTIONS,
    MISSING_VALUE_OPTIONS,
    preprocess_modeling_frame,
)
from dashboard.models.SARIMAX.ui.state import (
    clear_fit_results,
    clear_widget_state,
    MODEL_WIDGET_KEYS,
    state,
)

_SARIMAX_DATA_KEY_PREFIX = "sarimax_model"
_SARIMAX_DATA_NAMESPACE = "model_analysis.sarimax"
_HANDOFF_RESTORE_GUARD_KEY = f"{_SARIMAX_DATA_NAMESPACE}.handoff_restore"
SARIMAX_DATA_OVERVIEW_WIDGET_KEYS = overview_widget_keys(
    _SARIMAX_DATA_KEY_PREFIX
) + (
    f"{_SARIMAX_DATA_KEY_PREFIX}_preview_sheet",
    "sarimax_data_preprocessing",
    "sarimax_missing_value_method",
)

_DATA_PROCESSING_BASE_KEY = "data_processing_base_fingerprint"
_DATA_PROCESSING_SIGNATURE_KEY = "data_processing_signature"
_DATA_PROCESSING_FRAME_KEY = "data_processing_frame"
_DATA_PROCESSING_AUTO_START_KEY = "data_processing_auto_start"
_DATA_PROCESSING_WIDGET_KEYS = (
    "sarimax_data_preprocessing",
    "sarimax_missing_value_method",
)
_DATA_PROCESSING_WIDGET_STATE_KEYS = (
    *_DATA_PROCESSING_WIDGET_KEYS,
    "sarimax_start_processing_button",
)
_MODEL_WIDGET_KEYS_WITHOUT_DATA_PROCESSING = tuple(
    key
    for key in MODEL_WIDGET_KEYS
    if key not in _DATA_PROCESSING_WIDGET_STATE_KEYS
)


@dataclass(frozen=True)
class SARIMAXDataSnapshot:
    """独立动态回归模型页所需的原始文件与工作表快照。"""

    asset: FileAsset
    sheet: str | None


_SARIMAX_DATA_SOURCE = BuiltinDataSource(_SARIMAX_DATA_NAMESPACE)


def _on_dataset_replaced(st_obj) -> None:
    """模型文件或读取设置改变时，使已有模型结果和输入控件失效。"""

    if st_obj.session_state.pop(_HANDOFF_RESTORE_GUARD_KEY, False):
        return
    state.set("target_variable", None)
    state.set("exog_variables", ())
    state.set("training_time_range", None)
    state.set("response_log", False)
    state.set("future_exog_editor_signature", None)
    clear_fit_results()
    # 数据处理控件在数据输入组件中已经渲染；保留它们，避免点击“开始处理”
    # 后被回调清掉，导致模型输入元数据与实际处理规则不一致。
    clear_widget_state(st_obj, _MODEL_WIDGET_KEYS_WITHOUT_DATA_PROCESSING)


def _render_and_process_sarimax_data(
    st_obj,
    frame: pd.DataFrame,
    fingerprint: str,
) -> pd.DataFrame | None:
    """渲染数据处理控件，并按按钮提交处理后的数据集。"""

    base_fingerprint = state.get(_DATA_PROCESSING_BASE_KEY)
    if base_fingerprint != fingerprint:
        state.set(_DATA_PROCESSING_BASE_KEY, fingerprint)
        state.set(_DATA_PROCESSING_SIGNATURE_KEY, None)
        state.set(_DATA_PROCESSING_FRAME_KEY, None)
        if not state.get(_DATA_PROCESSING_AUTO_START_KEY, False):
            for key in _DATA_PROCESSING_WIDGET_STATE_KEYS:
                st_obj.session_state.pop(key, None)
            state.set("data_preprocessing", ())
            state.set("missing_value_method", "无")

    preprocessing_key, missing_value_key = _DATA_PROCESSING_WIDGET_KEYS
    processing_columns = st_obj.columns(2)
    with processing_columns[0]:
        preprocessing_kwargs = {
            "options": DATA_REPLACEMENT_OPTIONS,
            "key": preprocessing_key,
            "help": "可多选：去零将 0 值替换为缺失，去负将负值替换为缺失。",
        }
        if preprocessing_key not in st_obj.session_state:
            preprocessing_kwargs["default"] = list(DATA_REPLACEMENT_OPTIONS)
        preprocessing = tuple(
            st_obj.multiselect("数据替换", **preprocessing_kwargs)
        )
    with processing_columns[1]:
        stored_method = st_obj.session_state.get(
            missing_value_key,
            MISSING_VALUE_OPTIONS[0],
        )
        if stored_method not in MISSING_VALUE_OPTIONS:
            stored_method = MISSING_VALUE_OPTIONS[0]
            st_obj.session_state[missing_value_key] = stored_method
        missing_value_method = st_obj.selectbox(
            "缺失值处理",
            options=MISSING_VALUE_OPTIONS,
            index=MISSING_VALUE_OPTIONS.index(stored_method),
            key=missing_value_key,
            help=(
                "数据替换后对全部数值型变量应用缺失值处理；"
                "插值方法仅填补可根据现有观测推断的位置。"
            ),
        )
    state.set("data_preprocessing", preprocessing)
    state.set("missing_value_method", missing_value_method)

    processing_signature = (
        fingerprint,
        preprocessing,
        missing_value_method,
    )
    applied_signature = state.get(_DATA_PROCESSING_SIGNATURE_KEY)
    start_processing = st_obj.button(
        "开始处理",
        type="primary",
        key="sarimax_start_processing_button",
    )
    if start_processing or (
        state.get(_DATA_PROCESSING_AUTO_START_KEY, False)
        and applied_signature != processing_signature
    ):
        state.set(_DATA_PROCESSING_AUTO_START_KEY, False)
        with st_obj.spinner("正在解析和预处理数据..."):
            processed = preprocess_modeling_frame(
                frame,
                preprocessing=preprocessing,
                missing_value_method=missing_value_method,
            )
        state.set(_DATA_PROCESSING_FRAME_KEY, processed)
        state.set(_DATA_PROCESSING_SIGNATURE_KEY, processing_signature)
        st_obj.success("数据处理完成，可以继续设置模型参数。")
        return processed

    if applied_signature == processing_signature:
        processed = state.get(_DATA_PROCESSING_FRAME_KEY)
        if isinstance(processed, pd.DataFrame):
            return processed

    st_obj.info("请确认数据处理参数后，点击“开始处理”。")
    return None


_SARIMAX_DATA_INPUT = create_data_input_module(
    key_prefix=_SARIMAX_DATA_KEY_PREFIX,
    state_namespace=_SARIMAX_DATA_NAMESPACE,
    data_source=_SARIMAX_DATA_SOURCE,
    dataset_processor=_render_and_process_sarimax_data,
    on_dataset_replaced=_on_dataset_replaced,
    title="",
    show_preview=False,
)


def render_sarimax_data_input(st_obj) -> None:
    """渲染 SARIMAX 专属文件上传和读取设置。"""

    _SARIMAX_DATA_INPUT.render(st_obj)


def export_sarimax_data_snapshot() -> SARIMAXDataSnapshot | None:
    """导出当前 SARIMAX 自有文件和工作表，供独立页面交接。"""

    if state.get("dataset") is None:
        return None
    uploaded_file = st.session_state.get(
        f"{_SARIMAX_DATA_NAMESPACE}.upload.file"
    )
    if uploaded_file is None:
        return None
    content = uploaded_file.getvalue()
    fingerprint = _SARIMAX_DATA_SOURCE.current_fingerprint() or file_fingerprint(
        content
    )
    asset = FileAsset(
        slot=_SARIMAX_DATA_NAMESPACE,
        name=str(getattr(uploaded_file, "name", "未命名文件")),
        content=content,
        fingerprint=fingerprint,
    )
    return SARIMAXDataSnapshot(
        asset=asset,
        sheet=_SARIMAX_DATA_SOURCE.current_sheet(),
    )


def restore_sarimax_data_snapshot(snapshot: SARIMAXDataSnapshot) -> None:
    """把 SARIMAX 文件预置到当前会话，等待数据概览组件完成解析。"""

    if not isinstance(snapshot, SARIMAXDataSnapshot):
        raise TypeError("SARIMAX 数据快照类型无效")
    _SARIMAX_DATA_SOURCE.restore_file(
        snapshot.asset.content,
        snapshot.asset.name,
        sheet=snapshot.sheet,
    )


def mark_sarimax_handoff_restore(
    st_obj,
    snapshot: SARIMAXDataSnapshot,
    *,
    variable_name_row: int,
    data_start_row: int,
) -> None:
    """预置交接读取设置，避免首次渲染重置已复制的输入。"""

    restore_sarimax_data_snapshot(snapshot)
    state.set("source_fingerprint", snapshot.asset.fingerprint)
    try:
        raw_data = _SARIMAX_DATA_SOURCE.load_data(
            variable_name_row=variable_name_row - 1,
            data_start_row=data_start_row - 1,
            time_column=None,
        )
        if raw_data is not None:
            time_options = ("无", *[str(column) for column in raw_data.columns])
            state.set(
                "time_options_signature",
                (
                    snapshot.asset.fingerprint,
                    variable_name_row,
                    data_start_row,
                    time_options,
                ),
            )
    except Exception:
        # 首次组件渲染会再次读取并展示原始错误；这里不能吞掉交接流程。
        pass
    st_obj.session_state[_HANDOFF_RESTORE_GUARD_KEY] = True
    state.set(_DATA_PROCESSING_AUTO_START_KEY, True)


__all__ = [
    "SARIMAXDataSnapshot",
    "SARIMAX_DATA_OVERVIEW_WIDGET_KEYS",
    "export_sarimax_data_snapshot",
    "mark_sarimax_handoff_restore",
    "render_sarimax_data_input",
    "restore_sarimax_data_snapshot",
]
