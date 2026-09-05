"""Shared DuckDB-to-workbook writer for source-owned indicator sheets."""

from __future__ import annotations

import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def write_indicator_sheets(
    workbook_path: Path,
    sheets: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    """Atomically replace several wide indicator sheets in one workbook.

    Each sheet mapping contains `
ame``, ``title``, ``indicators``,
    ``metadata`` and ``rows``. Rows are ``(period, {indicator: value})``.
    """

    workbook_path = Path(workbook_path).resolve()
    if not workbook_path.is_file():
        raise FileNotFoundError(workbook_path)
    lock_path = workbook_path.parent / f"~${workbook_path.name}"
    if lock_path.exists():
        raise RuntimeError(f"请先关闭 Excel 工作簿：{lock_path}")

    sheet_specs = list(sheets)
    if not sheet_specs:
        return {}

    workbook = load_workbook(workbook_path, keep_links=True)
    counts: dict[str, int] = {}
    try:
        for spec in sheet_specs:
            sheet_name = str(spec["name"])
            indicators = [str(name) for name in spec["indicators"]]
            metadata = spec["metadata"]
            rows = sorted(spec["rows"], key=lambda item: item[0], reverse=True)
            if not rows:
                raise ValueError(f"{sheet_name} 没有可写入的数据")
            missing_metadata = [name for name in indicators if name not in metadata]
            if missing_metadata:
                raise ValueError(
                    f"{sheet_name} 缺少指标元数据：{', '.join(missing_metadata)}"
                )

            index = workbook.sheetnames.index(sheet_name) if sheet_name in workbook.sheetnames else len(workbook.sheetnames)
            if sheet_name in workbook.sheetnames:
                workbook.remove(workbook[sheet_name])
            worksheet = workbook.create_sheet(sheet_name, index)
            _write_sheet(worksheet, str(spec["title"]), indicators, metadata, rows)
            counts[sheet_name] = len(rows)

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{workbook_path.stem}.extended-",
                suffix=".tmp.xlsx",
                dir=workbook_path.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
            workbook.save(temporary)
            os.replace(temporary, workbook_path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    finally:
        workbook.close()
    return counts


def _write_sheet(
    worksheet,
    title: str,
    indicators: list[str],
    metadata: Mapping[str, Mapping[str, Any]],
    rows: list[tuple[Any, Mapping[str, Any]]],
) -> None:
    column_count = len(indicators) + 1
    worksheet.cell(row=1, column=1, value=title)
    worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=column_count)
    worksheet.cell(row=2, column=1, value="指标名称")
    worksheet.cell(row=3, column=1, value="频率")
    worksheet.cell(row=4, column=1, value="单位")
    worksheet.cell(row=5, column=1, value="来源")
    worksheet.cell(row=6, column=1, value="更新时间")

    updated_at = datetime.now()
    for column, name in enumerate(indicators, start=2):
        row_metadata = metadata[name]
        worksheet.cell(row=2, column=column, value=name)
        worksheet.cell(row=3, column=column, value=row_metadata["frequency"])
        worksheet.cell(row=4, column=column, value=row_metadata["unit"])
        worksheet.cell(row=5, column=column, value=row_metadata["source"])
        worksheet.cell(row=6, column=column, value=updated_at)

    for row_number, (period, values) in enumerate(rows, start=7):
        worksheet.cell(row=row_number, column=1, value=period)
        for column, name in enumerate(indicators, start=2):
            worksheet.cell(
                row=row_number,
                column=column,
                value=_excel_value(values.get(name)),
            )

    header_fill = PatternFill("solid", fgColor="D9EAF7")
    metadata_fill = PatternFill("solid", fgColor="E2F0D9")
    title_font = Font(name="Microsoft YaHei", size=11, bold=True, color="FFFFFF")
    header_font = Font(name="Microsoft YaHei", size=9, bold=True)
    body_font = Font(name="Microsoft YaHei", size=9)
    worksheet.cell(row=1, column=1).fill = PatternFill("solid", fgColor="1F4E78")
    worksheet.cell(row=1, column=1).font = title_font
    worksheet.cell(row=1, column=1).alignment = Alignment(horizontal="center")
    for row_number in range(2, 7):
        for cell in worksheet[row_number][:column_count]:
            cell.font = header_font
            cell.fill = header_fill if row_number == 2 else metadata_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row_number in range(7, worksheet.max_row + 1):
        for cell in worksheet[row_number][:column_count]:
            cell.font = body_font
        worksheet.cell(row=row_number, column=1).number_format = "yyyy-mm-dd"

    worksheet.column_dimensions["A"].width = 13
    for column in range(2, column_count + 1):
        worksheet.column_dimensions[get_column_letter(column)].width = 28
    worksheet.freeze_panes = "B7"
    worksheet.auto_filter.ref = f"A2:{get_column_letter(column_count)}{worksheet.max_row}"


def _excel_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, int, float, str)) or value is None:
        return value
    return float(value)
