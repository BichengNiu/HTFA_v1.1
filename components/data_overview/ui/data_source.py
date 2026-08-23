"""数据源协议与内置上传实现。

数据概览需要「上传文件 → DataFrame + 指纹 + 工作表」的数据来源。
默认使用包内 BuiltinDataSource（自带 file_uploader，命名空间
``{namespace}.upload``）；外部项目可注入自己的 DataSource 实现
（例如 HTFA 的侧边栏共享数据集适配器）。
"""

from __future__ import annotations

import hashlib
import io
import csv
from typing import Any, Protocol

import pandas as pd
import streamlit as st

SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls"]
_AUTO_TIME_COLUMN = object()


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


def _read_raw_rows(uploaded_file, sheet_name: str | None = None) -> list[list[Any]]:
    """读取原始行，不预设表头，保留前置说明行。"""
    content = uploaded_file.getvalue()
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if extension == "csv":
        last_error = None
        for encoding in ("utf-8", "gbk", "gb2312"):
            try:
                return [
                    list(row)
                    for row in csv.reader(
                        io.StringIO(content.decode(encoding), newline="")
                    )
                ]
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError(
            "无法解码 CSV 文件，请使用 UTF-8、GBK 或 GB2312 编码"
        ) from last_error
    if extension in {"xlsx", "xls"}:
        if sheet_name is None:
            with pd.ExcelFile(io.BytesIO(content)) as excel:
                sheet_name = excel.sheet_names[0]
        frame = pd.read_excel(
            io.BytesIO(content),
            sheet_name=sheet_name,
            header=None,
        )
        return frame.where(pd.notna(frame), None).values.tolist()
    raise ValueError(f"不支持的文件格式：{extension}")


def _is_blank(value: Any) -> bool:
    """判断原始单元格是否为空。"""
    return value is None or (isinstance(value, float) and pd.isna(value)) or (
        isinstance(value, str) and not value.strip()
    )


def _infer_numeric_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """把完全由数字组成的文本列恢复为数值列。"""
    result = frame.copy()
    for column in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[column]):
            continue
        converted = pd.to_numeric(result[column], errors="coerce")
        nonblank = result[column].notna()
        if converted[nonblank].notna().all():
            result[column] = converted
    return result


def _make_unique_column_names(names: list[str]) -> list[str]:
    """保留首个表头，重复表头按出现顺序追加 ``__2``、``__3``。"""
    used = set()
    occurrence: dict[str, int] = {}
    unique_names = []
    for base_name in names:
        occurrence[base_name] = occurrence.get(base_name, 0) + 1
        suffix_number = occurrence[base_name]
        candidate = (
            base_name
            if suffix_number == 1
            else f"{base_name}__{suffix_number}"
        )
        while candidate in used:
            occurrence[base_name] += 1
            suffix_number = occurrence[base_name]
            candidate = f"{base_name}__{suffix_number}"
        used.add(candidate)
        unique_names.append(candidate)
    return unique_names


def _parse_time_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """把用户指定列解析为时间列，无法完整解析时提示用户。"""
    if column not in frame.columns:
        raise ValueError(f"时间列不存在：{column}")
    values = frame[column]
    if pd.api.types.is_datetime64_any_dtype(values):
        return frame
    nonblank = values.notna() & values.astype(str).str.strip().ne("")
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    if not parsed.loc[nonblank].notna().all():
        raise ValueError(f"时间列“{column}”存在无法解析的值")
    result = frame.copy()
    result[column] = parsed
    return result


def _build_dataframe_from_rows(
    rows: list[list[Any]],
    *,
    variable_name_row: int = 0,
    data_start_row: int = 1,
    time_column: str | None | object = _AUTO_TIME_COLUMN,
) -> pd.DataFrame:
    """按 0-based 行号从原始行构建带变量名的数据框。"""
    if not isinstance(variable_name_row, int) or isinstance(variable_name_row, bool):
        raise ValueError("变量名行必须是整数")
    if not isinstance(data_start_row, int) or isinstance(data_start_row, bool):
        raise ValueError("数据开始行必须是整数")
    if variable_name_row < 0 or data_start_row <= variable_name_row:
        raise ValueError("数据开始行必须晚于变量名行")
    if variable_name_row >= len(rows) or data_start_row >= len(rows):
        raise ValueError("选择的行号超出数据范围")

    header = list(rows[variable_name_row])
    while header and _is_blank(header[-1]):
        header.pop()
    if not header:
        raise ValueError("变量名行为空")
    names = []
    for index, value in enumerate(header, start=1):
        if _is_blank(value):
            raise ValueError(f"变量名行第 {index} 列为空")
        names.append(str(value).strip())
    names = _make_unique_column_names(names)

    width = len(names)
    data_rows = []
    for row_number, row in enumerate(rows[data_start_row:], start=data_start_row + 1):
        values = list(row)
        if len(values) > width and any(
            not _is_blank(value) for value in values[width:]
        ):
            raise ValueError(f"第 {row_number} 行超过变量名行的列数")
        data_rows.append(values[:width] + [None] * max(0, width - len(values)))
    frame = pd.DataFrame(data_rows, columns=names)
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("数据开始行之后没有可读取的数据")
    frame = _infer_numeric_columns(frame)
    if time_column is _AUTO_TIME_COLUMN:
        return _parse_first_column_as_time(frame)
    if time_column is None:
        return frame
    return _parse_time_column(frame, time_column)


def _load_dataframe(
    uploaded_file,
    sheet_name: str | None = None,
    *,
    variable_name_row: int = 0,
    data_start_row: int = 1,
    time_column: str | None | object = _AUTO_TIME_COLUMN,
) -> pd.DataFrame:
    """按变量名行和数据开始行读取文件。"""
    rows = _read_raw_rows(uploaded_file, sheet_name=sheet_name)
    return _build_dataframe_from_rows(
        rows,
        variable_name_row=variable_name_row,
        data_start_row=data_start_row,
        time_column=time_column,
    )


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

        fingerprint = _fingerprint_file(uploaded_file)
        stored_fingerprint = st.session_state.get(self._key("fingerprint"), "")
        if not _fingerprint_matches(fingerprint, stored_fingerprint):
            sheets = None
            sheet = None
            raw_rows = []
            data = None
            read_error = None
            try:
                sheets = _list_excel_sheets(uploaded_file)
                sheet = sheets[0] if sheets else None
                raw_rows = _read_raw_rows(uploaded_file, sheet_name=sheet)
                data = _build_dataframe_from_rows(raw_rows)
            except Exception as exc:  # noqa: BLE001 - 用户可读的文件读取边界
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
                st_obj.warning(
                    "默认读取失败；请在数据预览中输入变量名行和数据开始行后重试。"
                )
                return {
                    "has_data": True,
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
            rows = _read_raw_rows(uploaded_file, sheet_name=self.current_sheet())
            st.session_state[self._key("raw_rows")] = rows
        return _build_dataframe_from_rows(
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
            raw_rows = _read_raw_rows(uploaded_file, sheet_name=sheet)
        except Exception as exc:  # noqa: BLE001 - 用户可读的读取边界
            st.error(f"工作表读取失败：{exc}")
            return
        try:
            data = _build_dataframe_from_rows(raw_rows)
        except Exception:
            # 保留原始工作表，允许数据预览中的行号设置完成解析。
            st.session_state.pop(self._key("data"), None)
            st.session_state[self._key("raw_rows")] = raw_rows
            st.session_state[self._key("sheet")] = sheet
            st.session_state[self._key("fingerprint")] = (
                f"{_fingerprint_file(uploaded_file)}::{sheet}"
            )
            return
        st.session_state[self._key("data")] = data
        st.session_state[self._key("raw_rows")] = raw_rows
        st.session_state[self._key("sheet")] = sheet
        st.session_state[self._key("fingerprint")] = (
            f"{_fingerprint_file(uploaded_file)}::{sheet}"
        )


def _fingerprint_matches(file_fingerprint: str, current: str) -> bool:
    """当前指纹是否属于该文件（兼容“文件指纹::工作表名”）。"""
    return current == file_fingerprint or current.startswith(
        f"{file_fingerprint}::"
    )


__all__ = [
    "BuiltinDataSource",
    "DataSource",
    "SUPPORTED_FILE_TYPES",
]
