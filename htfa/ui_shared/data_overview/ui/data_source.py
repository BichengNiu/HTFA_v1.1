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
from htfa.data.tabular import (
    FileParseError,
    TabularFileSnapshot,
    TabularInputSource,
    build_dataframe_from_rows,
)

SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]
_TABULAR_INPUT_SOURCE = TabularInputSource()


class DataSource(Protocol):
    """数据源协议：渲染控件并暴露一次读取状态快照。"""

    def render_uploader(self, st_obj, *, compact: bool = False) -> dict:
        """渲染上传控件；返回 {"has_data": bool, ...}。"""

    def snapshot(self) -> TabularFileSnapshot | None:
        """返回当前文件、工作表和原始行的纯读取快照。"""

    def load_data(
        self,
        *,
        variable_name_row: int = 0,
        data_start_row: int = 1,
        time_column: str | None = None,
    ) -> pd.DataFrame | None:
        """按变量名行和数据开始行从当前原始文件构建数据。"""

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
        for field in (
            "fingerprint", "sheets", "raw_rows", "data", "parse_error"
        ):
            st.session_state.pop(self._key(field), None)
        st.session_state[self._key("file_name")] = restored_file.name
        try:
            snapshot = _TABULAR_INPUT_SOURCE.read_source(
                content, restored_file.name, sheet_name=sheet
            )
        except FileParseError as exc:
            snapshot = TabularFileSnapshot(
                file_name=restored_file.name,
                fingerprint=file_fingerprint(content),
                sheets=None,
                sheet=None,
                raw_rows=[],
                frame=None,
                parse_error=str(exc),
            )
        self._store_snapshot(snapshot)

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
                "parse_error",
            ):
                st.session_state.pop(self._key(name), None)
            return {"has_data": False}

        content = uploaded_file.getvalue()
        fingerprint = file_fingerprint(content)
        stored_fingerprint = st.session_state.get(self._key("fingerprint"), "")
        if fingerprint != stored_fingerprint:
            read_error = None
            raw_rows = []
            try:
                snapshot = _TABULAR_INPUT_SOURCE.read_source(
                    content,
                    uploaded_file.name,
                    sheet_name=st.session_state.get(self._key("restored_sheet")),
                )
            except FileParseError as exc:
                snapshot = None
                read_error = str(exc)
            else:
                read_error = snapshot.parse_error
                raw_rows = snapshot.raw_rows
            st.session_state[self._key("file")] = uploaded_file
            st.session_state[self._key("file_name")] = uploaded_file.name
            st.session_state[self._key("fingerprint")] = fingerprint
            if snapshot is None:
                st.session_state[self._key("sheets")] = None
                st.session_state[self._key("sheet")] = None
                st.session_state[self._key("raw_rows")] = raw_rows
                st.session_state[self._key("parse_error")] = read_error
                st.session_state.pop(self._key("data"), None)
            else:
                self._store_snapshot(snapshot)
            if read_error is not None:
                st_obj.error(f"数据文件读取失败：{read_error}")
                return {
                    "has_data": bool(raw_rows),
                    "file_name": uploaded_file.name,
                    "error": read_error,
                }

        snapshot = self.snapshot()
        if snapshot is None:
            return {"has_data": False, "file_name": uploaded_file.name}
        if snapshot.parse_error is not None:
            st_obj.error(f"数据文件读取失败：{snapshot.parse_error}")
            return {
                "has_data": bool(snapshot.raw_rows),
                "file_name": uploaded_file.name,
                "error": snapshot.parse_error,
            }

        if not compact:
            data = snapshot.frame
            if data is not None:
                st_obj.caption(f"{data.shape[0]:,} 行 × {data.shape[1]:,} 列")
        return {"has_data": True, "file_name": uploaded_file.name}

    def snapshot(self) -> TabularFileSnapshot | None:
        fingerprint = st.session_state.get(self._key("fingerprint"), "")
        if not fingerprint:
            return None
        return TabularFileSnapshot(
            file_name=st.session_state.get(self._key("file_name"), ""),
            fingerprint=fingerprint,
            sheets=st.session_state.get(self._key("sheets")),
            sheet=st.session_state.get(self._key("sheet")),
            raw_rows=st.session_state.get(self._key("raw_rows"), []),
            frame=st.session_state.get(self._key("data")),
            parse_error=st.session_state.get(self._key("parse_error")),
        )

    def _store_snapshot(self, snapshot: TabularFileSnapshot) -> None:
        st.session_state[self._key("fingerprint")] = snapshot.fingerprint
        st.session_state[self._key("sheets")] = snapshot.sheets
        st.session_state[self._key("sheet")] = snapshot.sheet
        st.session_state[self._key("raw_rows")] = snapshot.raw_rows
        st.session_state[self._key("data")] = snapshot.frame
        st.session_state[self._key("parse_error")] = snapshot.parse_error

    def load_data(
        self,
        *,
        variable_name_row: int = 0,
        data_start_row: int = 1,
        time_column: str | None = None,
    ) -> pd.DataFrame | None:
        """按变量名行和数据开始行从当前原始文件构建数据。"""
        snapshot = self.snapshot()
        if snapshot is None:
            return None
        return build_dataframe_from_rows(
            snapshot.raw_rows,
            variable_name_row=variable_name_row,
            data_start_row=data_start_row,
            time_column=time_column,
        )

    def select_sheet(self, sheet: str) -> None:
        uploaded_file = st.session_state.get(self._key("file"))
        if uploaded_file is None:
            return
        try:
            snapshot = _TABULAR_INPUT_SOURCE.read_source(
                uploaded_file.getvalue(), uploaded_file.name, sheet_name=sheet
            )
        except FileParseError as exc:
            st.error(f"工作表读取失败：{exc}")
            st.session_state.pop(self._key("data"), None)
            st.session_state[self._key("raw_rows")] = []
            st.session_state[self._key("sheet")] = sheet
            return
        self._store_snapshot(snapshot)
        if snapshot.parse_error is not None:
            st.error(f"工作表读取失败：{snapshot.parse_error}")


__all__ = [
    "BuiltinDataSource",
    "DataSource",
    "SUPPORTED_FILE_TYPES",
]
