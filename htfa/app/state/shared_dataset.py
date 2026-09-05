# -*- coding: utf-8 -*-
"""三个数据模块共用的会话级数据集状态。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import streamlit as st

from htfa.data.tabular.file_parsing import (
    FileParseError,
    build_dataframe_from_rows,
    list_excel_sheets,
    read_raw_rows,
)
from htfa.workspace import FileAsset, NamedBytesIO, SessionWorkspace


STATE_PREFIX = "htfa.shared_dataset"
SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]


@dataclass(frozen=True)
class SharedDatasetSnapshot:
    """可在另一 Streamlit 会话中恢复的共享数据文件快照。"""

    asset: FileAsset
    sheet: str | None


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
    return st.session_state.get(_state_key("fingerprint"), "")


def get_shared_dataset_sheets() -> Optional[list[str]]:
    """获取当前会话上传文件的工作表名列表（非 Excel 为 None）。"""
    return st.session_state.get(_state_key("sheets"))


def get_shared_dataset_sheet() -> Optional[str]:
    """获取当前会话选中的工作表名。"""
    return st.session_state.get(_state_key("sheet"))


def export_shared_dataset_snapshot() -> SharedDatasetSnapshot | None:
    """导出当前共享文件和已选工作表，供短生命周期页面交接使用。"""

    asset = _workspace().get_asset("shared")
    if asset is None:
        return None
    return SharedDatasetSnapshot(asset=asset, sheet=get_shared_dataset_sheet())


def restore_shared_dataset_snapshot(snapshot: SharedDatasetSnapshot) -> None:
    """将共享数据快照恢复到当前会话。"""

    if not isinstance(snapshot, SharedDatasetSnapshot):
        raise TypeError("共享数据快照类型无效")

    _clear_shared_derived_state()
    uploaded_file = NamedBytesIO(snapshot.asset.content, snapshot.asset.name)
    _workspace().put_asset("shared", uploaded_file)
    content = uploaded_file.getvalue()
    sheets = list_excel_sheets(content, uploaded_file.name)
    sheet = snapshot.sheet if snapshot.sheet in (sheets or []) else None
    if sheet is None and sheets:
        sheet = sheets[0]

    raw_rows = read_raw_rows(content, uploaded_file.name, sheet_name=sheet)
    try:
        data = build_dataframe_from_rows(raw_rows)
    except FileParseError:
        data = None

    fingerprint = snapshot.asset.fingerprint
    st.session_state[_state_key("data")] = data
    st.session_state[_state_key("raw_rows")] = raw_rows
    st.session_state[_state_key("fingerprint")] = fingerprint
    st.session_state[_state_key("sheets")] = sheets
    st.session_state[_state_key("sheet")] = sheet


def select_shared_dataset_sheet(sheet: str) -> bool:
    """切换到指定工作表并重载共享数据；成功返回 True。"""
    uploaded_file = get_shared_dataset_file()
    if uploaded_file is None:
        return False
    _clear_dependent_analysis_state()
    st.session_state.pop(_state_key("data"), None)
    try:
        raw_rows = read_raw_rows(
            uploaded_file.getvalue(), uploaded_file.name, sheet_name=sheet
        )
    except FileParseError:
        st.session_state[_state_key("raw_rows")] = []
        st.session_state[_state_key("sheet")] = sheet
        return False

    try:
        data = build_dataframe_from_rows(raw_rows)
    except FileParseError:
        data = None
    st.session_state[_state_key("data")] = data
    st.session_state[_state_key("raw_rows")] = raw_rows
    st.session_state[_state_key("file_name")] = uploaded_file.name
    st.session_state[_state_key("sheet")] = sheet
    return True


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
    st_obj, *, compact: bool = False
) -> dict:
    """渲染共享数据集上传器，并在文件变更时更新共享状态。

    compact=True 时隐藏「共享数据集」标题、已加载提示与行数列数
    小字（用于页面主区域内嵌场景，如单变量分析的数据概览）。
    """
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
            st_obj.caption(f"当前会话文件：{asset.name}")
            if st_obj.button("清除当前文件", key="htfa_shared_dataset_clear"):
                clear_shared_dataset()
                return {"show_upload": True, "has_data": False}
            return {
                "show_upload": True,
                "has_data": True,
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
    fingerprint = update.asset.fingerprint
    if update.changed or not get_shared_dataset_fingerprint():
        sheets = None
        sheet = None
        raw_rows = []
        error = None
        try:
            _clear_shared_derived_state()
            content = active_file.getvalue()
            sheets = list_excel_sheets(content, active_file.name)
            sheet = sheets[0] if sheets else None
            raw_rows = read_raw_rows(content, active_file.name, sheet_name=sheet)
            data = build_dataframe_from_rows(raw_rows)
        except FileParseError as exc:
            data = None
            error = str(exc)
            st_obj.error(f"共享数据集读取失败：{error}")

        st.session_state[_state_key("data")] = data
        st.session_state[_state_key("raw_rows")] = raw_rows
        st.session_state[_state_key("fingerprint")] = fingerprint
        st.session_state[_state_key("sheets")] = sheets
        st.session_state[_state_key("sheet")] = sheet
        if data is None:
            return {
                "show_upload": True,
                "has_data": bool(raw_rows),
                "file_name": active_file.name,
                "error": error,
            }

    if not compact:
        st_obj.success(f"已加载：{active_file.name}")
        data = get_shared_dataset_data()
        if data is not None:
            st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
    return {"show_upload": True, "has_data": True, "file_name": active_file.name}


__all__ = [
    "SharedDatasetSnapshot",
    "clear_shared_dataset",
    "export_shared_dataset_snapshot",
    "get_shared_dataset_data",
    "get_shared_dataset_file",
    "get_shared_dataset_fingerprint",
    "get_shared_dataset_name",
    "get_shared_dataset_raw_rows",
    "get_shared_dataset_row_count",
    "get_shared_dataset_sheet",
    "get_shared_dataset_sheets",
    "render_shared_dataset_uploader",
    "restore_shared_dataset_snapshot",
    "select_shared_dataset_sheet",
]
