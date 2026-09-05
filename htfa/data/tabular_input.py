"""普通表格输入协议。

该模块只处理用户提供的普通 CSV/XLS/XLSX 表格，不应用经济工作簿的
指标字典、元数据或零值缺失规则。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from components.data_overview.core.file_parsing import (
    FileParseError,
    list_excel_sheets,
    load_dataframe,
)


ECONOMIC_WORKBOOK_SHEET = "指标字典"


def read_tabular_file(
    file_input: Any,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """按普通表格协议读取一个文件。

    CSV 形成一个 ``table``；Excel 的每个非空工作表形成一个独立表格。
    经济工作簿通过首个工作表名称被明确拒绝，调用方必须选择经济工作簿协议。
    """
    content = _read_bytes(file_input)
    file_name = str(
        getattr(file_input, "name", file_input)
        if not isinstance(file_input, bytes)
        else "table.xlsx"
    )
    file_name = Path(file_name).name
    suffix = file_name.rsplit(".", 1)[-1].lower()

    if suffix == "csv":
        frame = load_dataframe(content, file_name)
        if frame.empty:
            raise FileParseError("CSV 文件中没有可分析数据")
        return {"table": frame}, {}

    if suffix not in {"xlsx", "xls"}:
        raise FileParseError("仅支持 CSV、XLSX 和 XLS 文件")

    sheets = list_excel_sheets(content, file_name) or []
    if sheets and sheets[0] == ECONOMIC_WORKBOOK_SHEET:
        raise FileParseError(
            "检测到经济工作簿；请使用经济工作簿输入协议，不得用普通表格协议解析"
        )

    tables: dict[str, pd.DataFrame] = {}
    for sheet_name in sheets:
        frame = load_dataframe(
            content,
            file_name,
            sheet_name=sheet_name,
        )
        if not frame.empty:
            tables[sheet_name] = frame

    if not tables:
        raise FileParseError("工作簿中没有可分析的数据表")
    return tables, {}


def _read_bytes(file_input: Any) -> bytes:
    if isinstance(file_input, bytes):
        return file_input
    if isinstance(file_input, (str, Path)):
        return Path(file_input).read_bytes()
    if hasattr(file_input, "getvalue"):
        return file_input.getvalue()
    if hasattr(file_input, "read"):
        content = file_input.read()
        if hasattr(file_input, "seek"):
            file_input.seek(0)
        return content
    raise TypeError("表格输入必须是 bytes 或可读取的二进制文件对象")


__all__ = ["ECONOMIC_WORKBOOK_SHEET", "read_tabular_file"]
