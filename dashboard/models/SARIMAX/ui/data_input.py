"""SARIMAX 自有的数据读取入口，不依赖数据探索页面。"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st
from data_overview.core.file_parsing import file_fingerprint
from data_overview.ui.data_source import BuiltinDataSource
from data_overview.ui.widget_keys import overview_widget_keys

from dashboard.core.workspace import FileAsset
from dashboard.models.common.ui.data_input import create_data_input_module
from dashboard.models.SARIMAX.ui.state import (
    clear_fit_results,
    clear_widget_state,
    state,
)

_SARIMAX_DATA_KEY_PREFIX = "sarimax_model"
_SARIMAX_DATA_NAMESPACE = "model_analysis.sarimax"
_HANDOFF_RESTORE_GUARD_KEY = f"{_SARIMAX_DATA_NAMESPACE}.handoff_restore"
SARIMAX_DATA_OVERVIEW_WIDGET_KEYS = overview_widget_keys(
    _SARIMAX_DATA_KEY_PREFIX
) + (
    f"{_SARIMAX_DATA_KEY_PREFIX}_preview_sheet",
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
    state.set("data_preprocessing", ())
    state.set("response_log", False)
    state.set("future_exog_editor_signature", None)
    clear_fit_results()
    clear_widget_state(st_obj)


_SARIMAX_DATA_INPUT = create_data_input_module(
    key_prefix=_SARIMAX_DATA_KEY_PREFIX,
    state_namespace=_SARIMAX_DATA_NAMESPACE,
    data_source=_SARIMAX_DATA_SOURCE,
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


__all__ = [
    "SARIMAXDataSnapshot",
    "SARIMAX_DATA_OVERVIEW_WIDGET_KEYS",
    "export_sarimax_data_snapshot",
    "mark_sarimax_handoff_restore",
    "render_sarimax_data_input",
    "restore_sarimax_data_snapshot",
]
