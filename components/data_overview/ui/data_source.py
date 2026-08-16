"""数据源协议与内置上传实现。

数据概览需要「上传文件 → DataFrame + 指纹 + 工作表」的数据来源。
默认使用包内 BuiltinDataSource（自带 file_uploader，命名空间
``{namespace}.upload``）；外部项目可注入自己的 DataSource 实现
（例如 HTFA 的侧边栏共享数据集适配器）。
"""

from __future__ import annotations

import hashlib
import io
from typing import Any, Protocol

import pandas as pd
import streamlit as st

SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]


class DataSource(Protocol):
    """数据源接口：渲染上传控件并暴露当前数据集信息。"""

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        """渲染上传控件；返回 {"has_data": bool, ...}。"""

    def current_data(self) -> pd.DataFrame | None:
        """当前会话的数据框；未上传时为 None。"""

    def current_fingerprint(self) -> str:
        """当前文件内容指纹（用于缓存失效）。"""

    def current_name(self) -> str:
        """当前文件名。"""

    def sheets(self) -> list[str] | None:
        """Excel 工作表名列表（非 Excel 为 None）。"""

    def current_sheet(self) -> str | None:
        """当前选中的工作表名。"""

    def select_sheet(self, sheet: str) -> None:
        """切换工作表并重载数据。"""


def _fingerprint_file(uploaded_file) -> str:
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


def _list_excel_sheets(uploaded_file) -> list[str] | None:
    """Excel 文件返回工作表名列表；非 Excel 文件返回 None。"""
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    if extension not in {"xlsx", "xls"}:
        return None
    with pd.ExcelFile(io.BytesIO(uploaded_file.getvalue())) as excel:
        return list(excel.sheet_names)


def _load_dataframe(
    uploaded_file, sheet_name: str | None = None
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


class BuiltinDataSource:
    """包内默认数据源：内部 file_uploader + 指纹缓存。

    会话键命名空间为 ``{namespace}.upload.*``，与外部共享数据集
    互不干扰。
    """

    def __init__(self, namespace: str = "data_overview"):
        self.namespace = namespace

    def _key(self, name: str) -> str:
        return f"{self.namespace}.upload.{name}"

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        if not compact:
            st_obj.markdown("### 数据文件")
        uploaded_file = st_obj.file_uploader(
            "选择数据文件",
            type=SUPPORTED_FILE_TYPES,
            key=self._key("uploader"),
            help="CSV / XLSX / XLS；更换文件会重置本组件的分析状态。",
        )

        if uploaded_file is None:
            if st.session_state.get(self._key("data")) is not None:
                for name in ("file", "data", "file_name", "fingerprint", "sheets", "sheet"):
                    st.session_state.pop(self._key(name), None)
            return {"has_data": False}

        fingerprint = _fingerprint_file(uploaded_file)
        if st.session_state.get(self._key("fingerprint")) != fingerprint:
            try:
                sheets = _list_excel_sheets(uploaded_file)
                sheet = sheets[0] if sheets else None
                data = _load_dataframe(uploaded_file, sheet_name=sheet)
                data = data.dropna(how="all").dropna(axis=1, how="all")
                if data.empty:
                    raise ValueError("文件清理后为空")
            except Exception as exc:  # noqa: BLE001 - 用户可读的文件读取边界
                for name in ("file", "data", "file_name", "fingerprint", "sheets", "sheet"):
                    st.session_state.pop(self._key(name), None)
                st_obj.error(f"数据文件读取失败：{exc}")
                return {"has_data": False, "error": str(exc)}
            st.session_state[self._key("file")] = uploaded_file
            st.session_state[self._key("data")] = data
            st.session_state[self._key("file_name")] = uploaded_file.name
            st.session_state[self._key("fingerprint")] = fingerprint
            st.session_state[self._key("sheets")] = sheets
            st.session_state[self._key("sheet")] = sheet

        if not compact:
            data = self.current_data()
            if data is not None:
                st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
        return {"has_data": True, "file_name": uploaded_file.name}

    def current_data(self) -> pd.DataFrame | None:
        return st.session_state.get(self._key("data"))

    def current_fingerprint(self) -> str:
        return st.session_state.get(self._key("fingerprint"), "")

    def current_name(self) -> str:
        return st.session_state.get(self._key("file_name"), "")

    def sheets(self) -> list[str] | None:
        return st.session_state.get(self._key("sheets"))

    def current_sheet(self) -> str | None:
        return st.session_state.get(self._key("sheet"))

    def select_sheet(self, sheet: str) -> None:
        uploaded_file = st.session_state.get(self._key("file"))
        if uploaded_file is None:
            return
        try:
            data = _load_dataframe(uploaded_file, sheet_name=sheet)
            data = data.dropna(how="all").dropna(axis=1, how="all")
        except Exception as exc:  # noqa: BLE001 - 用户可读的读取边界
            st.error(f"工作表读取失败：{exc}")
            return
        st.session_state[self._key("data")] = data
        st.session_state[self._key("sheet")] = sheet


__all__ = [
    "BuiltinDataSource",
    "DataSource",
    "SUPPORTED_FILE_TYPES",
]
