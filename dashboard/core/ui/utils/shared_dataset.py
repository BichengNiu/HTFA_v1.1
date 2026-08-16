# -*- coding: utf-8 -*-
"""三个数据模块共用的会话级数据集状态。"""

from __future__ import annotations

import hashlib
import io
from typing import Optional

import pandas as pd
import streamlit as st


STATE_PREFIX = "dashboard.shared_dataset"
SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]


def _state_key(name: str) -> str:
    return f"{STATE_PREFIX}.{name}"


def fingerprint_file(uploaded_file) -> str:
    """返回文件名与内容共同决定的稳定指纹。"""
    content = uploaded_file.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    return f"{uploaded_file.name}:{len(content)}:{digest}"


def _parse_first_column_as_time(frame: pd.DataFrame) -> pd.DataFrame:
    """仅当第一列的全部有效值都是日期时才转换该列。"""

    if frame.empty or frame.shape[1] == 0:
        return frame

    first_column = frame.iloc[:, 0]
    if pd.api.types.is_datetime64_any_dtype(first_column):
        return frame
    if pd.api.types.is_numeric_dtype(first_column):
        return frame

    nonblank = first_column.notna() & first_column.astype(str).str.strip().ne("")
    if not nonblank.any():
        return frame

    parsed = pd.to_datetime(first_column, errors="coerce", format="mixed")
    if not parsed.loc[nonblank].notna().all():
        return frame

    result = frame.copy()
    result[result.columns[0]] = parsed
    return result


def list_excel_sheets(uploaded_file) -> Optional[list[str]]:
    """Excel 文件返回工作表名列表；非 Excel 文件返回 None。"""
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    if extension not in {"xlsx", "xls"}:
        return None
    with pd.ExcelFile(io.BytesIO(uploaded_file.getvalue())) as excel:
        return list(excel.sheet_names)


def load_shared_dataframe(
    uploaded_file, sheet_name: Optional[str] = None
) -> pd.DataFrame:
    """以通用时序表格式读取共享文件，第一列优先解析为时间列。"""
    content = uploaded_file.getvalue()
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if extension == "csv":
        last_error = None
        for encoding in ("utf-8", "gbk", "gb2312"):
            try:
                frame = pd.read_csv(io.StringIO(content.decode(encoding)))
                return _parse_first_column_as_time(frame)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError("无法解码 CSV 文件，请使用 UTF-8、GBK 或 GB2312 编码") from last_error
    if extension in {"xlsx", "xls"}:
        if sheet_name is None:
            with pd.ExcelFile(io.BytesIO(content)) as excel:
                sheet_name = excel.sheet_names[0]
        frame = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name)
        return _parse_first_column_as_time(frame)
    raise ValueError(f"不支持的文件格式：{extension}")


def get_shared_dataset_file():
    """获取当前会话的原始上传文件。"""
    return st.session_state.get(_state_key("file"))


def get_shared_dataset_data() -> Optional[pd.DataFrame]:
    """获取当前会话的通用 DataFrame。"""
    return st.session_state.get(_state_key("data"))


def get_shared_dataset_name() -> str:
    """获取当前会话数据集名称。"""
    return st.session_state.get(_state_key("file_name"), "")


def get_shared_dataset_fingerprint() -> str:
    """获取当前会话数据集指纹。"""
    return st.session_state.get(_state_key("fingerprint"), "")


def get_shared_dataset_sheets() -> Optional[list[str]]:
    """获取当前会话上传文件的工作表名列表（非 Excel 为 None）。"""
    return st.session_state.get(_state_key("sheets"))


def get_shared_dataset_sheet() -> Optional[str]:
    """获取当前会话选中的工作表名。"""
    return st.session_state.get(_state_key("sheet"))


def select_shared_dataset_sheet(sheet: str) -> bool:
    """切换到指定工作表并重载共享数据；成功返回 True。"""
    uploaded_file = get_shared_dataset_file()
    if uploaded_file is None:
        return False
    try:
        data = load_shared_dataframe(uploaded_file, sheet_name=sheet)
        data = data.dropna(how="all").dropna(axis=1, how="all")
        if data.empty:
            raise ValueError("工作表清理后为空")
    except Exception:
        return False
    _clear_dependent_analysis_state()
    st.session_state[_state_key("data")] = data
    st.session_state[_state_key("file_name")] = uploaded_file.name
    st.session_state[_state_key("fingerprint")] = (
        f"{fingerprint_file(uploaded_file)}::{sheet}"
    )
    st.session_state[_state_key("sheet")] = sheet
    return True


def _clear_dependent_analysis_state() -> None:
    """新文件进入后移除依赖旧数据的探索与模型分析结果。"""
    prefixes = (
        "tools.analysis.",
        "exploration.lead_lag.",
        "model_analysis.sarimax.",
    )
    for key in list(st.session_state):
        if str(key).startswith(prefixes):
            del st.session_state[key]


def clear_shared_dataset() -> None:
    """清除共享数据集及其派生的探索结果。"""
    for key in list(st.session_state):
        if str(key).startswith(f"{STATE_PREFIX}."):
            del st.session_state[key]
    _clear_dependent_analysis_state()


def _fingerprint_matches(file_fingerprint: str, current: str) -> bool:
    """当前指纹是否属于该文件（兼容“文件指纹::工作表名”形式）。"""
    return current == file_fingerprint or current.startswith(
        f"{file_fingerprint}::"
    )


def render_shared_dataset_uploader(st_obj, *, compact: bool = False) -> dict:
    """渲染共享数据集上传器，并在文件变更时更新共享状态。

    compact=True 时隐藏「共享数据集」标题、已加载提示与行数列数
    小字（用于页面主区域内嵌场景，如模型分析的数据概览）。
    """
    if not compact:
        st_obj.markdown("### 共享数据集")
    uploaded_file = st_obj.file_uploader(
        "选择数据文件",
        type=SUPPORTED_FILE_TYPES,
        key="dashboard_shared_dataset_uploader",
        help="数据预览、监测分析、数据探索和模型分析会共同使用此文件。",
    )

    if uploaded_file is None:
        if get_shared_dataset_file() is not None:
            clear_shared_dataset()
        if not compact:
            st_obj.caption(
                "支持 CSV、XLS、XLSX；更换文件会清除数据探索与模型分析的历史结果。"
            )
        return {"show_upload": True, "has_data": False}

    fingerprint = fingerprint_file(uploaded_file)
    if not _fingerprint_matches(fingerprint, get_shared_dataset_fingerprint()):
        try:
            sheets = list_excel_sheets(uploaded_file)
            sheet = sheets[0] if sheets else None
            data = load_shared_dataframe(uploaded_file, sheet_name=sheet)
            data = data.dropna(how="all").dropna(axis=1, how="all")
            if data.empty:
                raise ValueError("文件清理后为空")
        except Exception as exc:
            clear_shared_dataset()
            st_obj.error(f"共享数据集读取失败：{exc}")
            return {"show_upload": True, "has_data": False, "error": str(exc)}

        _clear_dependent_analysis_state()
        st.session_state[_state_key("file")] = uploaded_file
        st.session_state[_state_key("data")] = data
        st.session_state[_state_key("file_name")] = uploaded_file.name
        st.session_state[_state_key("fingerprint")] = fingerprint
        st.session_state[_state_key("sheets")] = sheets
        st.session_state[_state_key("sheet")] = sheet

    if not compact:
        st_obj.success(f"已加载：{uploaded_file.name}")
        data = get_shared_dataset_data()
        st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
    return {"show_upload": True, "has_data": True, "file_name": uploaded_file.name}


__all__ = [
    "clear_shared_dataset",
    "fingerprint_file",
    "get_shared_dataset_data",
    "get_shared_dataset_file",
    "get_shared_dataset_fingerprint",
    "get_shared_dataset_name",
    "get_shared_dataset_sheet",
    "get_shared_dataset_sheets",
    "list_excel_sheets",
    "render_shared_dataset_uploader",
    "select_shared_dataset_sheet",
]
