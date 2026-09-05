"""经济工作簿目标指标读取的纯规则实现。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from ..core.workbook_parser import normalize_indicator_name


METADATA_LABELS = {
    1: "指标名称",
    2: "频率",
    3: "单位",
    4: "来源",
    5: "更新时间",
}


@dataclass(frozen=True)
class SheetSeriesMetadata:
    """一条经济工作簿序列的来源与口径。"""

    display_name: str
    indicator_name: str
    frequency: str
    unit: str
    source: str
    updated_at: str
    sheet_name: str


def optional_text(value: Any) -> str:
    """把可选单元格值规范为文本。"""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    return str(value).strip()


def format_updated_at(value: Any) -> str:
    """把更新时间单元格规范为 YYYY-MM-DD 文本。"""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return optional_text(value)
    if pd.isna(timestamp):
        return ""
    return timestamp.strftime("%Y-%m-%d")


def workbook_buffer(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> tuple[BytesIO, str]:
    """把工作簿输入规范为带来源名的内存文件。"""
    if isinstance(file_input, (str, Path)):
        path = Path(file_input)
        return BytesIO(path.read_bytes()), path.name
    if isinstance(file_input, bytes):
        return BytesIO(file_input), file_name or "经济数据库.xlsx"
    if hasattr(file_input, "getvalue"):
        content = file_input.getvalue()
    elif hasattr(file_input, "read"):
        content = file_input.read()
    else:
        raise TypeError("工作簿输入必须是路径或可读取的二进制文件对象")
    if not isinstance(content, bytes):
        raise TypeError("工作簿输入必须提供 bytes 内容")
    name = file_name or getattr(file_input, "name", "经济数据库.xlsx")
    return BytesIO(content), Path(str(name)).name


@contextmanager
def open_workbook(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> Iterator[tuple[pd.ExcelFile, str]]:
    """打开经济工作簿并在退出时关闭 ExcelFile。"""
    buffer, source_name = workbook_buffer(file_input, file_name=file_name)
    excel_file = pd.ExcelFile(buffer)
    try:
        yield excel_file, source_name
    finally:
        excel_file.close()


def validate_sheet(raw: pd.DataFrame, sheet_name: str) -> None:
    """校验目标数据 sheet 的五行元数据标签。"""
    if raw.shape[0] < 7 or raw.shape[1] < 2:
        raise ValueError(f"sheet“{sheet_name}”不符合第2至第6行元数据协议")
    for row_index, expected in METADATA_LABELS.items():
        actual = optional_text(raw.iloc[row_index, 0])
        if actual != expected:
            raise ValueError(
                f"sheet“{sheet_name}”第{row_index + 1}行首列应为“{expected}”，"
                f"实际为“{actual or '空'}”"
            )


def parse_target_sheet(
    excel_file: pd.ExcelFile,
    *,
    sheet_name: str,
    targets: tuple[tuple[str, str], ...],
    allowed_frequencies: set[str],
    expected_unit: str,
    zero_is_missing: bool = True,
) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
    """按目标、频率和单位从一个正式数据 sheet 提取序列。"""
    if sheet_name not in excel_file.sheet_names:
        raise ValueError(f"工作簿缺少“{sheet_name}”sheet")

    raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
    validate_sheet(raw, sheet_name)

    normalized_targets = {
        normalize_indicator_name(indicator_name): display_name
        for display_name, indicator_name in targets
    }
    candidate_columns: dict[str, list[int]] = {}
    for column_index in range(1, raw.shape[1]):
        normalized_name = normalize_indicator_name(raw.iloc[1, column_index])
        if normalized_name not in normalized_targets:
            continue
        display_name = normalized_targets[normalized_name]
        candidate_columns.setdefault(display_name, []).append(column_index)

    matching_columns: dict[str, int] = {}
    for display_name, columns in candidate_columns.items():
        compatible_columns = [
            column_index
            for column_index in columns
            if optional_text(raw.iloc[2, column_index]) in allowed_frequencies
            and optional_text(raw.iloc[3, column_index]) == expected_unit
            and bool(optional_text(raw.iloc[4, column_index]))
        ]
        if len(compatible_columns) > 1:
            indicator_name = normalize_indicator_name(raw.iloc[1, columns[0]])
            raise ValueError(
                f"sheet“{sheet_name}”包含重复目标指标：{indicator_name}"
            )
        if len(compatible_columns) == 1:
            matching_columns[display_name] = compatible_columns[0]
        elif len(columns) == 1:
            matching_columns[display_name] = columns[0]
        else:
            indicator_name = normalize_indicator_name(raw.iloc[1, columns[0]])
            raise ValueError(
                f"sheet“{sheet_name}”的重复指标“{indicator_name}”中，"
                "没有唯一符合频率、单位和来源要求的列"
            )

    missing = [
        display_name
        for display_name, _ in targets
        if display_name not in matching_columns
    ]
    if missing:
        raise ValueError(f"sheet“{sheet_name}”缺少指标：{', '.join(missing)}")

    data_block = raw.iloc[6:, :].dropna(how="all")
    dates = pd.to_datetime(data_block.iloc[:, 0], errors="coerce")
    if dates.isna().any():
        row_number = int(dates[dates.isna()].index[0]) + 1
        raise ValueError(f"sheet“{sheet_name}”第{row_number}行日期无效")
    if dates.duplicated().any():
        raise ValueError(f"sheet“{sheet_name}”包含重复日期")

    series_map: dict[str, pd.Series] = {}
    metadata: dict[str, SheetSeriesMetadata] = {}
    for display_name, column_index in matching_columns.items():
        indicator_name = normalize_indicator_name(raw.iloc[1, column_index])
        frequency = optional_text(raw.iloc[2, column_index])
        unit = optional_text(raw.iloc[3, column_index])
        source = optional_text(raw.iloc[4, column_index])
        updated_at = format_updated_at(raw.iloc[5, column_index])

        if frequency not in allowed_frequencies:
            raise ValueError(
                f"指标“{indicator_name}”频率应为"
                f"{'/'.join(sorted(allowed_frequencies))}，实际为“{frequency}”"
            )
        if unit != expected_unit:
            raise ValueError(
                f"指标“{indicator_name}”单位应为“{expected_unit}”，"
                f"实际为“{unit or '空'}”"
            )
        if not source:
            raise ValueError(f"指标“{indicator_name}”来源不能为空")

        raw_values = data_block.iloc[:, column_index]
        numeric = pd.to_numeric(raw_values, errors="coerce")
        invalid = (
            raw_values.notna()
            & raw_values.astype(str).str.strip().ne("")
            & numeric.isna()
        )
        if invalid.any():
            row_number = int(invalid[invalid].index[0]) + 1
            raise ValueError(
                f"sheet“{sheet_name}”指标“{indicator_name}”"
                f"第{row_number}行不是数值"
            )

        values = numeric.mask(numeric.eq(0)) if zero_is_missing else numeric
        series = pd.Series(
            values.to_numpy(),
            index=pd.DatetimeIndex(dates),
            name=display_name,
        ).dropna().sort_index()
        if series.empty:
            raise ValueError(f"指标“{indicator_name}”没有非零有效观测")
        series_map[display_name] = series
        metadata[display_name] = SheetSeriesMetadata(
            display_name=display_name,
            indicator_name=indicator_name,
            frequency=frequency,
            unit=unit,
            source=source,
            updated_at=updated_at,
            sheet_name=sheet_name,
        )

    ordered_names = [display_name for display_name, _ in targets]
    frame = pd.concat(
        [series_map[name] for name in ordered_names],
        axis=1,
        sort=False,
    ).sort_index()
    return frame, metadata


__all__ = [
    "METADATA_LABELS",
    "SheetSeriesMetadata",
    "format_updated_at",
    "open_workbook",
    "optional_text",
    "parse_target_sheet",
    "validate_sheet",
    "workbook_buffer",
]
