"""纯表格文件读取与 DataFrame 构建。"""

from __future__ import annotations

import csv
import io
from hashlib import sha256
from typing import Any

import pandas as pd


class FileParseError(ValueError):
    """用户输入文件无法读取或无法按指定结构解析。"""


_AUTO_TIME_COLUMN = object()
_EXCEL_EXTENSIONS = {"xlsx", "xls"}


def file_fingerprint(content: bytes) -> str:
    """返回只由文件内容决定的稳定 SHA-256 指纹。"""
    _validate_content(content)
    return sha256(content).hexdigest()


def list_excel_sheets(content: bytes, file_name: str) -> list[str] | None:
    """返回 Excel 文件的工作表名；非 Excel 文件返回 None。"""
    _validate_content(content)
    extension = _file_extension(file_name)
    if extension not in _EXCEL_EXTENSIONS:
        return None
    try:
        with pd.ExcelFile(io.BytesIO(content)) as excel:
            return list(excel.sheet_names)
    except Exception as exc:  # noqa: BLE001 - 统一用户可读的文件读取边界
        raise FileParseError(f"无法读取 Excel 文件：{exc}") from exc


def read_raw_rows(
    content: bytes, file_name: str, sheet_name: str | None = None
) -> list[list[Any]]:
    """读取原始行，不预设表头并保留前置说明行。"""
    _validate_content(content)
    extension = _file_extension(file_name)

    if extension == "csv":
        last_error: UnicodeDecodeError | None = None
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
            except csv.Error as exc:
                raise FileParseError(f"无法解析 CSV 文件：{exc}") from exc
        raise FileParseError(
            "无法解码 CSV 文件，请使用 UTF-8、GBK 或 GB2312 编码"
        ) from last_error

    if extension in _EXCEL_EXTENSIONS:
        try:
            if sheet_name is None:
                with pd.ExcelFile(io.BytesIO(content)) as excel:
                    sheet_name = excel.sheet_names[0]
            frame = pd.read_excel(
                io.BytesIO(content),
                sheet_name=sheet_name,
                header=None,
            )
        except Exception as exc:  # noqa: BLE001 - 统一用户可读的文件读取边界
            raise FileParseError(f"无法读取 Excel 文件：{exc}") from exc
        return frame.where(pd.notna(frame), None).values.tolist()

    raise FileParseError(f"不支持的文件格式：{extension}")


def build_dataframe_from_rows(
    rows: list[list[Any]],
    *,
    variable_name_row: int = 0,
    data_start_row: int = 1,
    time_column: str | None | object = _AUTO_TIME_COLUMN,
) -> pd.DataFrame:
    """按 0-based 行号从原始行构建带变量名的数据框。"""
    if not isinstance(variable_name_row, int) or isinstance(
        variable_name_row, bool
    ):
        raise FileParseError("变量名行必须是整数")
    if not isinstance(data_start_row, int) or isinstance(data_start_row, bool):
        raise FileParseError("数据开始行必须是整数")
    if variable_name_row < 0 or data_start_row <= variable_name_row:
        raise FileParseError("数据开始行必须晚于变量名行")
    if variable_name_row >= len(rows) or data_start_row >= len(rows):
        raise FileParseError("选择的行号超出数据范围")

    header = list(rows[variable_name_row])
    while header and _is_blank(header[-1]):
        header.pop()
    if not header:
        raise FileParseError("变量名行为空")

    names = []
    for index, value in enumerate(header, start=1):
        if _is_blank(value):
            raise FileParseError(f"变量名行第 {index} 列为空")
        names.append(str(value).strip())
    names = _make_unique_column_names(names)

    width = len(names)
    data_rows = []
    for row_number, row in enumerate(rows[data_start_row:], start=data_start_row + 1):
        values = list(row)
        if len(values) > width and any(
            not _is_blank(value) for value in values[width:]
        ):
            raise FileParseError(f"第 {row_number} 行超过变量名行的列数")
        data_rows.append(values[:width] + [None] * max(0, width - len(values)))

    frame = pd.DataFrame(data_rows, columns=names)
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    if frame.empty or frame.shape[1] == 0:
        raise FileParseError("数据开始行之后没有可读取的数据")

    frame = _infer_numeric_columns(frame)
    if time_column is _AUTO_TIME_COLUMN:
        return _parse_first_column_as_time(frame)
    if time_column is None:
        return frame
    return _parse_time_column(frame, time_column)


def load_dataframe(
    content: bytes,
    file_name: str,
    sheet_name: str | None = None,
    *,
    variable_name_row: int = 0,
    data_start_row: int = 1,
    time_column: str | None | object = _AUTO_TIME_COLUMN,
    raw_rows: list[list[Any]] | None = None,
) -> pd.DataFrame:
    """按变量名行和数据开始行从文件内容构建 DataFrame。"""
    rows = (
        read_raw_rows(content, file_name, sheet_name=sheet_name)
        if raw_rows is None
        else raw_rows
    )
    return build_dataframe_from_rows(
        rows,
        variable_name_row=variable_name_row,
        data_start_row=data_start_row,
        time_column=time_column,
    )


def _file_extension(file_name: str) -> str:
    return str(file_name).rsplit(".", 1)[-1].lower()


def _validate_content(content: bytes) -> None:
    if not isinstance(content, bytes):
        raise TypeError("文件内容必须是 bytes")


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
        nonblank = result[column].map(lambda value: not _is_blank(value))
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
    """把用户指定列解析为时间列，无法完整解析时抛出解析错误。"""
    if column not in frame.columns:
        raise FileParseError(f"时间列不存在：{column}")
    values = frame[column]
    if pd.api.types.is_datetime64_any_dtype(values):
        return frame
    nonblank = values.notna() & values.astype(str).str.strip().ne("")
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    if not parsed.loc[nonblank].notna().all():
        raise FileParseError(f"时间列“{column}”存在无法解析的值")
    result = frame.copy()
    result[column] = parsed
    return result


__all__ = [
    "FileParseError",
    "build_dataframe_from_rows",
    "file_fingerprint",
    "list_excel_sheets",
    "load_dataframe",
    "read_raw_rows",
]
