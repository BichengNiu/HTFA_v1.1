# -*- coding: utf-8 -*-
"""三个数据模块共用的会话级数据集状态。"""

from __future__ import annotations

from typing import Literal, Optional

import pandas as pd
import streamlit as st

from htfa.data.economic_workbook import EconomicWorkbookReader
from htfa.data.tabular import (
    FileParseError,
    TabularFileSnapshot,
    TabularInputSource,
)
from htfa.workspace import DatasetSnapshot, NamedBytesIO, SessionWorkspace


STATE_PREFIX = "htfa.shared_dataset"
SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]
SharedDatasetProtocol = Literal["tabular", "economic"]
_TABULAR_INPUT_SOURCE = TabularInputSource()
_ECONOMIC_WORKBOOK_READER = EconomicWorkbookReader(
    "shared_dataset",
    "app.shared_dataset",
)


def _state_key(name: str) -> str:
    return f"{STATE_PREFIX}.{name}"


def _workspace() -> SessionWorkspace:
    return SessionWorkspace(st.session_state)


def get_shared_dataset_row_count() -> int:
    """返回当前工作表的原始行数。"""
    return len(st.session_state.get(_state_key("raw_rows"), []))


def get_shared_dataset_raw_rows() -> list[list[object]] | None:
    """返回当前工作表已缓存的原始行；没有缓存时返回 ``None``。"""
    return st.session_state.get(_state_key("raw_rows"))


def get_shared_dataset_file():
    """获取当前会话的原始上传文件内存视图。"""
    return _workspace().open_asset("shared")


def get_shared_dataset_data() -> Optional[pd.DataFrame]:
    """获取当前会话的通用 DataFrame。"""
    return st.session_state.get(_state_key("data"))


def get_shared_dataset_name() -> str:
    """获取当前会话数据集名称。"""
    asset = _workspace().get_asset("shared")
    return asset.name if asset is not None else ""


def get_shared_dataset_fingerprint() -> str:
    """获取当前会话数据集指纹。"""
    asset = _workspace().get_asset("shared")
    return asset.fingerprint if asset is not None else ""


def get_shared_dataset_sheets() -> Optional[list[str]]:
    """获取当前会话上传文件的工作表名列表（非 Excel 为 None）。"""
    return st.session_state.get(_state_key("sheets"))


def get_shared_dataset_sheet() -> Optional[str]:
    """获取当前会话选中的工作表名。"""
    return st.session_state.get(_state_key("sheet"))


def get_shared_dataset_parse_error() -> Optional[str]:
    """获取当前工作表默认读取失败时的可见错误。"""
    return st.session_state.get(_state_key("parse_error"))


def get_shared_dataset_protocol() -> SharedDatasetProtocol | None:
    """返回当前共享文件已通过的明确输入协议。"""
    protocol = st.session_state.get(_state_key("protocol"))
    return protocol if protocol in {"tabular", "economic"} else None


def get_shared_dataset_snapshot() -> TabularFileSnapshot | None:
    """返回共享数据源的统一读取快照。"""
    if get_shared_dataset_protocol() != "tabular":
        return None
    fingerprint = get_shared_dataset_fingerprint()
    if not fingerprint:
        return None
    return TabularFileSnapshot(
        file_name=get_shared_dataset_name(),
        fingerprint=fingerprint,
        sheets=get_shared_dataset_sheets(),
        sheet=get_shared_dataset_sheet(),
        raw_rows=get_shared_dataset_raw_rows() or [],
        frame=get_shared_dataset_data(),
        parse_error=get_shared_dataset_parse_error(),
    )


def export_shared_dataset_snapshot() -> DatasetSnapshot | None:
    """导出当前共享文件和已选工作表，供短生命周期页面交接使用。"""

    if get_shared_dataset_protocol() != "tabular":
        return None
    asset = _workspace().get_asset("shared")
    if asset is None:
        return None
    return DatasetSnapshot(
        asset=asset,
        sheet=get_shared_dataset_sheet(),
        protocol="tabular",
    )


def restore_shared_dataset_snapshot(snapshot: DatasetSnapshot) -> None:
    """将共享数据快照恢复到当前会话。"""

    if not isinstance(snapshot, DatasetSnapshot):
        raise TypeError("共享数据快照类型无效")
    if snapshot.protocol != "tabular":
        raise ValueError("共享数据快照不是普通表格协议")

    _clear_shared_derived_state()
    uploaded_file = NamedBytesIO(snapshot.asset.content, snapshot.asset.name)
    _workspace().put_asset("shared", uploaded_file)
    raw_rows: list[list[object]] = []
    parse_error: str | None = None
    try:
        source = _TABULAR_INPUT_SOURCE.read_source(
            uploaded_file.getvalue(),
            uploaded_file.name,
            sheet_name=snapshot.sheet,
        )
    except FileParseError as exc:
        source = None
        parse_error = str(exc)

    if source is None:
        st.session_state[_state_key("data")] = None
        st.session_state[_state_key("raw_rows")] = raw_rows
        st.session_state[_state_key("sheets")] = None
        st.session_state[_state_key("sheet")] = None
        st.session_state[_state_key("parse_error")] = (
            parse_error or "共享数据集无法按普通表格协议读取"
        )
        return
    _store_shared_source(source)


def select_shared_dataset_sheet(sheet: str) -> bool:
    """切换到指定工作表并重载共享数据；成功返回 True。"""
    if get_shared_dataset_protocol() != "tabular":
        return False
    uploaded_file = get_shared_dataset_file()
    if uploaded_file is None:
        return False
    _clear_dependent_analysis_state()
    st.session_state.pop(_state_key("data"), None)
    try:
        source = _TABULAR_INPUT_SOURCE.read_source(
            uploaded_file.getvalue(), uploaded_file.name, sheet_name=sheet
        )
    except FileParseError:
        st.session_state[_state_key("raw_rows")] = []
        st.session_state[_state_key("sheet")] = sheet
        return False

    _store_shared_source(source)
    return True


def _store_shared_source(source) -> None:
    """把纯读取快照写入共享会话状态。"""

    st.session_state[_state_key("data")] = source.frame
    st.session_state[_state_key("raw_rows")] = source.raw_rows
    st.session_state[_state_key("file_name")] = source.file_name
    st.session_state[_state_key("sheets")] = source.sheets
    st.session_state[_state_key("sheet")] = source.sheet
    st.session_state[_state_key("parse_error")] = source.parse_error
    st.session_state[_state_key("protocol")] = "tabular"


def _read_shared_file(
    file_input,
    protocol: SharedDatasetProtocol,
) -> str | None:
    """按指定协议校验共享文件，并写入该协议的衍生状态。"""

    _clear_shared_derived_state()
    try:
        if protocol == "tabular":
            source = _TABULAR_INPUT_SOURCE.read_source(
                file_input,
                file_input.name,
            )
            _store_shared_source(source)
            return source.parse_error

        _ECONOMIC_WORKBOOK_READER.read(file_input)
    except (OSError, TypeError, ValueError) as exc:
        st.session_state[_state_key("data")] = None
        st.session_state[_state_key("raw_rows")] = []
        st.session_state[_state_key("sheets")] = None
        st.session_state[_state_key("sheet")] = None
        st.session_state[_state_key("parse_error")] = str(exc)
        st.session_state[_state_key("protocol")] = protocol
        return str(exc)

    st.session_state[_state_key("data")] = None
    st.session_state[_state_key("raw_rows")] = []
    st.session_state[_state_key("sheets")] = None
    st.session_state[_state_key("sheet")] = None
    st.session_state[_state_key("parse_error")] = None
    st.session_state[_state_key("protocol")] = protocol
    return None


def _validate_protocol(protocol: SharedDatasetProtocol) -> None:
    if protocol not in {"tabular", "economic"}:
        raise ValueError(f"不支持的共享数据协议：{protocol}")


def _clear_dependent_analysis_state() -> None:
    """新文件进入后移除依赖旧数据的数据探索结果。"""
    prefixes = (
        "exploration.dataset.",
        "tools.analysis.",
        "exploration.lead_lag.",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            del st.session_state[key]
def _clear_shared_page_snapshots() -> None:
    """清理依赖共享文件的页面输入快照。"""
    prefixes = (
        "workspace.pages.exploration.",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            del st.session_state[key]


def _clear_shared_derived_state() -> None:
    """保留文件资产，移除共享文件衍生状态与分析结果。"""
    for key in list(st.session_state):
        if str(key).startswith(f"{STATE_PREFIX}."):
            del st.session_state[key]
    _clear_shared_page_snapshots()
    _clear_dependent_analysis_state()


def clear_shared_dataset() -> None:
    """明确清除共享文件及其衍生的页面和分析状态。"""
    _workspace().clear_asset("shared")
    _clear_shared_derived_state()


def render_shared_dataset_uploader(
    st_obj,
    *,
    compact: bool = False,
    protocol: SharedDatasetProtocol = "tabular",
) -> dict:
    """渲染共享数据集上传器，并在文件变更时更新共享状态。

    compact=True 时隐藏「共享数据集」标题、已加载提示与行数列数
    小字（用于页面主区域内嵌场景，如单变量分析的数据概览）。
    """
    _validate_protocol(protocol)
    if not compact:
        st_obj.markdown("### 共享数据集")
    uploaded_file = st_obj.file_uploader(
        "选择数据文件",
        type=SUPPORTED_FILE_TYPES,
        key="htfa_shared_dataset_uploader",
        help="数据预览、监测分析、数据探索和模型分析会共同使用此文件。",
    )

    if uploaded_file is None:
        asset = _workspace().get_asset("shared")
        if asset is not None:
            if get_shared_dataset_protocol() != protocol:
                error = _read_shared_file(
                    _workspace().open_asset("shared"),
                    protocol,
                )
                if error is not None:
                    st_obj.error(f"共享数据集读取失败：{error}")
            st_obj.caption(f"当前会话文件：{asset.name}")
            if st_obj.button("清除当前文件", key="htfa_shared_dataset_clear"):
                clear_shared_dataset()
                return {"show_upload": True, "has_data": False}
            current_error = get_shared_dataset_parse_error()
            if current_error is not None:
                return {
                    "show_upload": True,
                    "has_data": bool(get_shared_dataset_raw_rows()),
                    "file_name": asset.name,
                    "error": current_error,
                }
            return {
                "show_upload": True,
                "has_data": protocol == "economic"
                or get_shared_dataset_data() is not None,
                "file_name": asset.name,
            }
        if not compact:
            st_obj.caption(
                "支持 CSV、XLS、XLSX；更换文件会清除数据探索与模型分析的历史结果。"
            )
        return {"show_upload": True, "has_data": False}

    update = _workspace().put_asset("shared", uploaded_file)
    active_file = _workspace().open_asset("shared")
    if active_file is None:  # pragma: no cover - put_asset 成功后的防御边界
        raise RuntimeError("共享文件资产未能保存")
    if (
        update.changed
        or get_shared_dataset_protocol() != protocol
        or not get_shared_dataset_fingerprint()
    ):
        error = _read_shared_file(active_file, protocol)
        if error is not None:
            st_obj.error(f"共享数据集读取失败：{error}")
        data = get_shared_dataset_data()
        if error is not None:
            return {
                "show_upload": True,
                "has_data": bool(get_shared_dataset_raw_rows()),
                "file_name": active_file.name,
                "error": error,
            }

    current_error = get_shared_dataset_parse_error()
    if current_error is not None:
        st_obj.error(f"共享数据集读取失败：{current_error}")
        return {
            "show_upload": True,
            "has_data": bool(get_shared_dataset_raw_rows()),
            "file_name": active_file.name,
            "error": current_error,
        }

    if not compact:
        st_obj.success(f"已加载：{active_file.name}")
        data = get_shared_dataset_data()
        if data is not None:
            st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
    return {
        "show_upload": True,
        "has_data": protocol == "economic" or data is not None,
        "file_name": active_file.name,
    }


__all__ = [
    "DatasetSnapshot",
    "clear_shared_dataset",
    "export_shared_dataset_snapshot",
    "get_shared_dataset_data",
    "get_shared_dataset_file",
    "get_shared_dataset_fingerprint",
    "get_shared_dataset_name",
    "get_shared_dataset_parse_error",
    "get_shared_dataset_protocol",
    "get_shared_dataset_raw_rows",
    "get_shared_dataset_row_count",
    "get_shared_dataset_sheet",
    "get_shared_dataset_sheets",
    "get_shared_dataset_snapshot",
    "render_shared_dataset_uploader",
    "restore_shared_dataset_snapshot",
    "select_shared_dataset_sheet",
]
