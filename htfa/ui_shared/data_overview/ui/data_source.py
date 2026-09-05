"""数据源协议与内置上传实现。

数据概览需要「上传文件 → DataFrame + 指纹 + 工作表」的数据来源。
默认使用包内 BuiltinDataSource（自带 file_uploader，命名空间
``{namespace}.upload``）；外部项目可注入自己的 DataSource 实现
（例如 HTFA 的侧边栏共享数据集适配器）。
"""

from __future__ import annotations

from io import BytesIO
from typing import Protocol

import pandas as pd
import streamlit as st

from htfa.data.file_content import file_fingerprint
from htfa.data.tabular.file_parsing import (
    FileParseError,
    build_dataframe_from_rows,
    list_excel_sheets,
    read_raw_rows,
)

SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]


class DataSource(Protocol):
    """数据源接口：渲染上传控件并暴露当前数据集信息。"""

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        """渲染上传控件；返回 {"has_data": bool, ...}。"""

    def current_data(self) -> pd.DataFrame | None:
        """当前会话的数据框；未上传时为 None。"""

    def load_data(
        self,
        *,
        variable_name_row: int = 0,
        data_start_row: int = 1,
        time_column: str | None = None,
    ) -> pd.DataFrame | None:
        """按变量名行和数据开始行从当前原始文件构建数据。"""

    def row_count(self) -> int:
        """返回当前工作表的可选原始行数。"""

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


class BuiltinDataSource:
    """包内默认数据源：内部 file_uploader + 指纹缓存。

    会话键命名空间为 ``{namespace}.upload.*``，与外部共享数据集
    互不干扰。
    """

    def __init__(self, namespace: str = "data_overview"):
        self.namespace = namespace

    def _key(self, name: str) -> str:
        return f"{self.namespace}.upload.{name}"

    def restore_file(
        self,
        content: bytes,
        name: str,
        *,
        sheet: str | None = None,
    ) -> None:
        """预置一个交接文件，供没有原上传器状态的新会话继续读取。"""

        if not isinstance(content, bytes):
            raise TypeError("恢复文件内容必须为 bytes")
        restored_file = BytesIO(content)
        restored_file.name = str(name)
        st.session_state[self._key("restored_file")] = restored_file
        st.session_state[self._key("file")] = restored_file
        st.session_state[self._key("restored_sheet")] = sheet
        st.session_state[self._key("sheet")] = sheet
        for field in ("fingerprint", "sheets", "raw_rows", "data"):
            st.session_state.pop(self._key(field), None)

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        if not compact:
            st_obj.markdown("### 数据文件")
        uploaded_file = st_obj.file_uploader(
            "选择数据文件",
            type=SUPPORTED_FILE_TYPES,
            key=self._key("uploader"),
            help="CSV / XLSX / XLS；更换文件会重置本组件的分析状态。",
        )

        restored_file = st.session_state.get(self._key("restored_file"))
        if uploaded_file is None and restored_file is not None:
            uploaded_file = restored_file
        elif uploaded_file is not None:
            st.session_state.pop(self._key("restored_file"), None)
            st.session_state.pop(self._key("restored_sheet"), None)

        if uploaded_file is None:
            for name in (
                "file",
                "data",
                "raw_rows",
                "file_name",
                "fingerprint",
                "sheets",
                "sheet",
            ):
                st.session_state.pop(self._key(name), None)
            return {"has_data": False}

        content = uploaded_file.getvalue()
        fingerprint = file_fingerprint(content)
        stored_fingerprint = st.session_state.get(self._key("fingerprint"), "")
        if fingerprint != stored_fingerprint:
            sheets = None
            sheet = None
            raw_rows = []
            data = None
            read_error = None
            try:
                sheets = list_excel_sheets(content, uploaded_file.name)
                restored_sheet = st.session_state.get(self._key("restored_sheet"))
                sheet = (
                    restored_sheet
                    if restored_sheet in (sheets or [])
                    else (sheets[0] if sheets else None)
                )
                raw_rows = read_raw_rows(content, uploaded_file.name, sheet_name=sheet)
                data = build_dataframe_from_rows(raw_rows)
            except FileParseError as exc:
                read_error = str(exc)
            st.session_state[self._key("file")] = uploaded_file
            st.session_state[self._key("file_name")] = uploaded_file.name
            st.session_state[self._key("fingerprint")] = fingerprint
            st.session_state[self._key("sheets")] = sheets
            st.session_state[self._key("sheet")] = sheet
            st.session_state[self._key("raw_rows")] = raw_rows
            if data is None:
                st.session_state.pop(self._key("data"), None)
            else:
                st.session_state[self._key("data")] = data
            if read_error is not None:
                st_obj.error(f"数据文件读取失败：{read_error}")
                return {
                    "has_data": bool(raw_rows),
                    "file_name": uploaded_file.name,
                    "error": read_error,
                }

        if not compact:
            data = self.current_data()
            if data is not None:
                st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
        return {"has_data": True, "file_name": uploaded_file.name}

    def current_data(self) -> pd.DataFrame | None:
        return st.session_state.get(self._key("data"))

    def load_data(
        self,
        *,
        variable_name_row: int = 0,
        data_start_row: int = 1,
        time_column: str | None = None,
    ) -> pd.DataFrame | None:
        """按变量名行和数据开始行从当前原始文件构建数据。"""
        uploaded_file = st.session_state.get(self._key("file"))
        if uploaded_file is None:
            return None
        rows = st.session_state.get(self._key("raw_rows"))
        if rows is None:
            rows = read_raw_rows(
                uploaded_file.getvalue(),
                uploaded_file.name,
                sheet_name=self.current_sheet(),
            )
            st.session_state[self._key("raw_rows")] = rows
        return build_dataframe_from_rows(
            rows,
            variable_name_row=variable_name_row,
            data_start_row=data_start_row,
            time_column=time_column,
        )

    def row_count(self) -> int:
        return len(st.session_state.get(self._key("raw_rows"), []))

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
            raw_rows = read_raw_rows(
                uploaded_file.getvalue(), uploaded_file.name, sheet_name=sheet
            )
        except FileParseError as exc:
            st.error(f"工作表读取失败：{exc}")
            st.session_state.pop(self._key("data"), None)
            st.session_state[self._key("raw_rows")] = []
            st.session_state[self._key("sheet")] = sheet
            return
        try:
            data = build_dataframe_from_rows(raw_rows)
        except FileParseError:
            st.session_state.pop(self._key("data"), None)
            st.session_state[self._key("raw_rows")] = raw_rows
            st.session_state[self._key("sheet")] = sheet
            return
        st.session_state[self._key("data")] = data
        st.session_state[self._key("raw_rows")] = raw_rows
        st.session_state[self._key("sheet")] = sheet


__all__ = [
    "BuiltinDataSource",
    "DataSource",
    "SUPPORTED_FILE_TYPES",
]
