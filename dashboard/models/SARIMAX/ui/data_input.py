"""动态回归各模型 Tab 的独立数据读取入口。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st
from data_overview.core.file_parsing import file_fingerprint
from data_overview.ui.data_source import BuiltinDataSource
from data_overview.ui.widget_keys import overview_widget_keys

from htfa.workspace import FileAsset
from dashboard.models.common.ui.data_input import create_data_input_module
from dashboard.models.SARIMAX.core.data_loader import (
    DATA_REPLACEMENT_OPTIONS,
    MISSING_VALUE_OPTIONS,
    preprocess_modeling_frame,
)
from dashboard.models.SARIMAX.ui.state import ModelPageScope, SARIMAX_SCOPE


@dataclass(frozen=True)
class SARIMAXDataSnapshot:
    """SARIMAX 独立窗口所需的原始文件与工作表快照。"""

    asset: FileAsset
    sheet: str | None


@dataclass
class ModelDataInput:
    """按模型 Tab 隔离文件、预处理和数据概览控件。"""

    scope: ModelPageScope
    data_source: BuiltinDataSource = field(init=False)
    overview_widget_keys: tuple[str, ...] = field(init=False)
    _module: object = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.data_source = BuiltinDataSource(self.scope.namespace)
        self.overview_widget_keys = overview_widget_keys(self.scope.data_key_prefix) + (
            f"{self.scope.data_key_prefix}_preview_sheet",
            self.scope.key("data_preprocessing"),
            self.scope.key("missing_value_method"),
        )
        self._module = create_data_input_module(
            key_prefix=self.scope.data_key_prefix,
            state_namespace=self.scope.namespace,
            data_source=self.data_source,
            dataset_processor=self._render_and_process_data,
            on_dataset_replaced=self._on_dataset_replaced,
            title="",
            show_preview=False,
        )

    @property
    def _processing_widget_keys(self) -> tuple[str, str]:
        return (
            self.scope.key("data_preprocessing"),
            self.scope.key("missing_value_method"),
        )

    @property
    def _processing_widget_state_keys(self) -> tuple[str, ...]:
        return (*self._processing_widget_keys, self.scope.key("start_processing_button"))

    def render(self, st_obj) -> None:
        self._module.render(st_obj)

    def _on_dataset_replaced(self, st_obj) -> None:
        """文件或读取设置改变时只清空本模型 Tab 的状态。"""
        state = self.scope.state
        handoff_guard = f"{self.scope.namespace}.handoff_restore"
        if (
            st_obj.session_state.pop(handoff_guard, False)
            and state.get("dataset") is not None
        ):
            # 交接成功建立新数据集时保留恢复的模型输入和结果；
            # 交接解析失败时 dataset 仍为 None，必须继续清空旧状态。
            return
        state.set("target_variable", None)
        state.set("exog_variables", ())
        state.set("exog_log_names", ())
        state.set("training_time_range", None)
        state.set("response_log", False)
        state.set("intervention_analysis", False)
        state.set("intervention_config", None)
        state.set("future_exog_editor_signature", None)
        self.scope.clear_fit_results()
        self.scope.clear_widget_state(
            st_obj,
            tuple(
                key for key in self.scope.widget_keys
                if key not in self._processing_widget_state_keys
            ),
        )
        exog_log_prefix = f"{self.scope.key_prefix}_exog_log_"
        for key in list(st_obj.session_state.keys()):
            if isinstance(key, str) and key.startswith(exog_log_prefix):
                st_obj.session_state.pop(key, None)

    def _render_and_process_data(
        self,
        st_obj,
        frame: pd.DataFrame,
        fingerprint: str,
    ) -> pd.DataFrame | None:
        """渲染并提交当前模型 Tab 的数据预处理设置。"""
        state = self.scope.state
        base_key = "data_processing_base_fingerprint"
        signature_key = "data_processing_signature"
        frame_key = "data_processing_frame"
        auto_start_key = "data_processing_auto_start"
        if state.get(base_key) != fingerprint:
            state.set(base_key, fingerprint)
            state.set(signature_key, None)
            state.set(frame_key, None)
            if not state.get(auto_start_key, False):
                for key in self._processing_widget_state_keys:
                    st_obj.session_state.pop(key, None)
                state.set("data_preprocessing", ())
                state.set("missing_value_method", "无")

        preprocessing_key, missing_value_key = self._processing_widget_keys
        columns = st_obj.columns(2)
        with columns[0]:
            kwargs = {
                "options": DATA_REPLACEMENT_OPTIONS,
                "key": preprocessing_key,
                "help": "可多选：去零将 0 值替换为缺失，去负将负值替换为缺失。",
            }
            if preprocessing_key not in st_obj.session_state:
                kwargs["default"] = list(DATA_REPLACEMENT_OPTIONS)
            preprocessing = tuple(st_obj.multiselect("数据替换", **kwargs))
        with columns[1]:
            stored = st_obj.session_state.get(missing_value_key, MISSING_VALUE_OPTIONS[0])
            if stored not in MISSING_VALUE_OPTIONS:
                stored = MISSING_VALUE_OPTIONS[0]
                st_obj.session_state[missing_value_key] = stored
            missing_value_method = st_obj.selectbox(
                "缺失值处理", options=MISSING_VALUE_OPTIONS,
                index=MISSING_VALUE_OPTIONS.index(stored), key=missing_value_key,
                help="数据替换后对全部数值型变量应用缺失值处理。",
            )
        state.set("data_preprocessing", preprocessing)
        state.set("missing_value_method", missing_value_method)
        signature = (fingerprint, preprocessing, missing_value_method)
        applied_signature = state.get(signature_key)
        start = st_obj.button("开始处理", type="primary", key=self.scope.key("start_processing_button"))
        if start or (state.get(auto_start_key, False) and applied_signature != signature):
            state.set(auto_start_key, False)
            with st_obj.spinner("正在解析和预处理数据..."):
                processed = preprocess_modeling_frame(
                    frame, preprocessing=preprocessing, missing_value_method=missing_value_method,
                )
            state.set(frame_key, processed)
            state.set(signature_key, signature)
            st_obj.success("数据处理完成，可以继续设置模型参数。")
            return processed
        if applied_signature == signature:
            processed = state.get(frame_key)
            if isinstance(processed, pd.DataFrame):
                return processed
        st_obj.info("请确认数据处理参数后，点击“开始处理”。")
        return None


_MODEL_DATA_INPUTS = {scope.namespace: ModelDataInput(scope) for scope in (SARIMAX_SCOPE,)}


def get_model_data_input(scope: ModelPageScope) -> ModelDataInput:
    """返回指定模型 Tab 的隔离数据输入实例。"""
    model_input = _MODEL_DATA_INPUTS.get(scope.namespace)
    if model_input is None:
        model_input = ModelDataInput(scope)
        _MODEL_DATA_INPUTS[scope.namespace] = model_input
    return model_input


def render_model_data_input(st_obj, scope: ModelPageScope) -> None:
    get_model_data_input(scope).render(st_obj)


_SARIMAX_MODEL_DATA = get_model_data_input(SARIMAX_SCOPE)
SARIMAX_DATA_OVERVIEW_WIDGET_KEYS = _SARIMAX_MODEL_DATA.overview_widget_keys


def render_sarimax_data_input(st_obj) -> None:
    """兼容既有 SARIMAX 页面入口。"""
    render_model_data_input(st_obj, SARIMAX_SCOPE)


def export_sarimax_data_snapshot() -> SARIMAXDataSnapshot | None:
    """导出当前 SARIMAX 文件和工作表，供独立窗口交接。"""
    if SARIMAX_SCOPE.state.get("dataset") is None:
        return None
    uploaded_file = st.session_state.get(f"{SARIMAX_SCOPE.namespace}.upload.file")
    if uploaded_file is None:
        return None
    content = uploaded_file.getvalue()
    source = _SARIMAX_MODEL_DATA.data_source
    fingerprint = source.current_fingerprint() or file_fingerprint(content)
    return SARIMAXDataSnapshot(
        asset=FileAsset(
            slot=SARIMAX_SCOPE.namespace,
            name=str(getattr(uploaded_file, "name", "未命名文件")),
            content=content,
            fingerprint=fingerprint,
        ),
        sheet=source.current_sheet(),
    )


def restore_sarimax_data_snapshot(snapshot: SARIMAXDataSnapshot) -> None:
    """把 SARIMAX 文件预置到当前会话。"""
    if not isinstance(snapshot, SARIMAXDataSnapshot):
        raise TypeError("SARIMAX 数据快照类型无效")
    _SARIMAX_MODEL_DATA.data_source.restore_file(
        snapshot.asset.content, snapshot.asset.name, sheet=snapshot.sheet,
    )


def mark_sarimax_handoff_restore(
    st_obj, snapshot: SARIMAXDataSnapshot, *, variable_name_row: int, data_start_row: int,
) -> None:
    """预置 SARIMAX 独立窗口的文件和读取设置。"""
    restore_sarimax_data_snapshot(snapshot)
    source = _SARIMAX_MODEL_DATA.data_source
    state = SARIMAX_SCOPE.state
    state.set("source_fingerprint", snapshot.asset.fingerprint)
    try:
        raw_data = source.load_data(
            variable_name_row=variable_name_row - 1, data_start_row=data_start_row - 1,
            time_column=None,
        )
        if raw_data is not None:
            state.set(
                "time_options_signature",
                (snapshot.asset.fingerprint, snapshot.sheet or "none",
                 variable_name_row, data_start_row,
                 ("无", *[str(column) for column in raw_data.columns])),
            )
    except Exception:
        pass
    st_obj.session_state[f"{SARIMAX_SCOPE.namespace}.handoff_restore"] = True
    state.set("data_processing_auto_start", True)


__all__ = [
    "ModelDataInput", "SARIMAXDataSnapshot", "SARIMAX_DATA_OVERVIEW_WIDGET_KEYS",
    "export_sarimax_data_snapshot", "get_model_data_input", "mark_sarimax_handoff_restore",
    "render_model_data_input", "render_sarimax_data_input", "restore_sarimax_data_snapshot",
]
