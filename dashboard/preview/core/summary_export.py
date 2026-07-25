"""数据摘要 Excel 导出。"""

import io

import pandas as pd
from openpyxl.styles import Alignment, Font

from dashboard.preview.core.calculation_rules import (
    group_indicators_by_calculation,
)


def build_summary_workbook(summary_table: pd.DataFrame) -> bytes:
    """生成包含数据摘要和计算口径说明的 Excel 文件。"""
    growth_indicators, difference_indicators = group_indicators_by_calculation(
        summary_table
    )
    note_table = pd.DataFrame(
        [
            {
                '计算方式': '按增速计算',
                '公式': '（本期值 - 对比期值）/ 对比期值',
                '适用指标': '\n'.join(growth_indicators) if growth_indicators else '无',
                '说明': '计算结果按百分比理解。',
            },
            {
                '计算方式': '按减差形式计算',
                '公式': '本期值 - 对比期值',
                '适用指标': (
                    '\n'.join(difference_indicators)
                    if difference_indicators else '无'
                ),
                '说明': '单位为“%”的指标，计算结果按百分点理解。',
            },
        ]
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        summary_table.to_excel(writer, sheet_name='数据摘要', index=False)
        note_table.to_excel(writer, sheet_name='口径说明', index=False)

        _format_summary_sheet(writer.sheets['数据摘要'])
        _format_note_sheet(writer.sheets['口径说明'])

    return buffer.getvalue()


def _format_summary_sheet(worksheet) -> None:
    """设置摘要工作表列宽。"""
    for column in worksheet.columns:
        max_length = max(
            (len(str(cell.value)) for cell in column if cell.value is not None),
            default=0,
        )
        worksheet.column_dimensions[column[0].column_letter].width = min(
            max_length + 2,
            50,
        )


def _format_note_sheet(worksheet) -> None:
    """设置口径说明工作表的可读性格式。"""
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')

    widths = {'A': 18, 'B': 36, 'C': 60, 'D': 48}
    for column, width in widths.items():
        worksheet.column_dimensions[column].width = width

    for row in worksheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
