"""普通表格输入协议的唯一读取实现。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from htfa.data.file_content import file_fingerprint

from .file_parsing import (
    ECONOMIC_WORKBOOK_SHEET,
    FileParseError,
    TabularFileSnapshot,
    _prepare_tabular_input,
    build_dataframe_from_rows,
    list_excel_sheets,
    load_dataframe,
    read_raw_rows,
)


class TabularInputSource:
    """读取普通表格数据集，不携带经济工作簿业务规则。"""

    def read(
        self, file_input: Any, file_name: str | None = None
    ) -> dict[str, pd.DataFrame]:
        """读取普通表格中的非空数据表。"""

        content, resolved_name, extension = _prepare_tabular_input(
            file_input, file_name
        )
        if extension == "csv":
            frame = load_dataframe(content, resolved_name)
            if frame.empty:
                raise FileParseError("CSV 文件中没有可分析数据")
            return {"table": frame}
        if extension not in {"xlsx", "xls"}:
            raise FileParseError("仅支持 CSV、XLSX 和 XLS 文件")

        sheets = list_excel_sheets(content, resolved_name) or []
        self._reject_economic_workbook(sheets)
        tables: dict[str, pd.DataFrame] = {}
        for sheet_name in sheets:
            frame = load_dataframe(content, resolved_name, sheet_name=sheet_name)
            if not frame.empty:
                tables[sheet_name] = frame
        if not tables:
            raise FileParseError("工作簿中没有可分析的数据表")
        return tables

    def read_source(
        self,
        file_input: Any,
        file_name: str | None = None,
        *,
        sheet_name: str | None = None,
    ) -> TabularFileSnapshot:
        """读取普通表格原始行及当前工作表的默认解析快照。"""

        content, resolved_name, _ = _prepare_tabular_input(file_input, file_name)
        sheets = list_excel_sheets(content, resolved_name)
        self._reject_economic_workbook(sheets or [])
        selected_sheet = sheet_name
        if sheets:
            if selected_sheet is None:
                selected_sheet = sheets[0]
            elif selected_sheet not in sheets:
                raise FileParseError(f"工作表不存在：{selected_sheet}")
        elif selected_sheet is not None:
            raise FileParseError("非 Excel 文件不能选择工作表")
        raw_rows = read_raw_rows(content, resolved_name, sheet_name=selected_sheet)
        parse_error = None
        try:
            frame = build_dataframe_from_rows(raw_rows)
        except FileParseError as exc:
            frame = None
            parse_error = str(exc)
        return TabularFileSnapshot(
            file_name=resolved_name,
            fingerprint=file_fingerprint(content),
            sheets=sheets,
            sheet=selected_sheet,
            raw_rows=raw_rows,
            frame=frame,
            parse_error=parse_error,
        )

    @staticmethod
    def _reject_economic_workbook(sheets: list[str]) -> None:
        if ECONOMIC_WORKBOOK_SHEET in sheets:
            raise FileParseError(
                "检测到经济工作簿；请使用经济工作簿输入协议，不得用普通表格协议解析"
            )


__all__ = ["TabularInputSource"]
