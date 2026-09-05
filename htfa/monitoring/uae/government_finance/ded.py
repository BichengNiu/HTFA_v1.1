"""DED 迪拜当月新发执照数的月度柱状图。

``月度_DED`` 沿用页面的前六行元数据协议，但两列单位不同（企业“家”、许可“张”），
因此用定制 loader 读取（与 ``foreign_labor`` 的定制解析一致）。图表只展示「当月
新发执照数」（执照号筛重）单条柱，不再叠加「有发证活动企业数」。窗口由调用方给定
（与「财政金融」区块锚定到同一最新月，避开 DED 快照尾部欠计噪声）。
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.periods import within_month_window
from htfa.monitoring.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from htfa.monitoring.uae.sheet_reader import (
    METADATA_LABELS,
    SheetSeriesMetadata,
    format_updated_at,
    open_uae_workbook,
    optional_text,
)
from htfa.data.economic_workbook.core.workbook_parser import normalize_indicator_name
from Ts.TsPlots.style import GRAY


DED_SHEET = "月度_DED"

ENTERPRISES_INDICATOR = "迪拜:当月有发证活动的企业数(企业号筛重)"
LICENCES_INDICATOR = "迪拜:当月新发执照数(执照号筛重)"
ENTERPRISES_DISPLAY = "有发证活动企业数"
LICENCES_DISPLAY = "当月新发执照数"

DED_INDICATORS: tuple[tuple[str, str], ...] = (
    (ENTERPRISES_DISPLAY, ENTERPRISES_INDICATOR),
    (LICENCES_DISPLAY, LICENCES_INDICATOR),
)
ALLOWED_UNITS = {"家", "张"}


@dataclass(frozen=True)
class DedData:
    """迪拜企业发证活动与新发执照的月度序列及来源信息。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_ded_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> DedData:
    """读取 ``月度_DED`` 的有发证活动企业数与当月新发执照数两列。"""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        frame, metadata = _parse_ded_sheet(excel_file)

    return DedData(
        values=frame,
        metadata=metadata,
        source_name=source_name,
    )


def _clean_source(value: str) -> str:
    """去掉来源里的括号及括号内说明（如 "(commerce_number 按发照月去重)"）。"""

    return re.sub(r"[（(][^）)]*[）)]", "", value).strip()


def _parse_ded_sheet(
    excel_file: pd.ExcelFile,
) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
    """按前六行元数据协议严格解析 DED sheet（两列单位分别为家/张）。"""

    if DED_SHEET not in excel_file.sheet_names:
        raise ValueError(f"工作簿缺少“{DED_SHEET}”sheet")

    raw = pd.read_excel(excel_file, sheet_name=DED_SHEET, header=None)
    if raw.shape[0] < 7 or raw.shape[1] < 3:
        raise ValueError(f"sheet“{DED_SHEET}”不符合前六行元数据协议")
    for row_index, expected in METADATA_LABELS.items():
        actual = optional_text(raw.iloc[row_index, 0])
        if actual != expected:
            raise ValueError(
                f"sheet“{DED_SHEET}”第{row_index + 1}行首列应为“{expected}”，"
                f"实际为“{actual or '空'}”"
            )

    normalized_targets = {
        normalize_indicator_name(indicator_name): display_name
        for display_name, indicator_name in DED_INDICATORS
    }
    candidate_columns: dict[str, list[int]] = {}
    for column_index in range(1, raw.shape[1]):
        normalized_name = normalize_indicator_name(raw.iloc[1, column_index])
        if normalized_name in normalized_targets:
            candidate_columns.setdefault(
                normalized_targets[normalized_name], []
            ).append(column_index)

    matching_columns: dict[str, int] = {}
    for display_name, indicator_name in DED_INDICATORS:
        columns = candidate_columns.get(display_name, [])
        compatible = [
            column_index
            for column_index in columns
            if optional_text(raw.iloc[2, column_index]) in {"月", "月度"}
            and optional_text(raw.iloc[3, column_index]) in ALLOWED_UNITS
            and bool(optional_text(raw.iloc[4, column_index]))
        ]
        if len(compatible) != 1:
            if not columns:
                raise ValueError(f"sheet“{DED_SHEET}”缺少指标：{indicator_name}")
            raise ValueError(
                f"指标“{indicator_name}”应有唯一一列月度、家/张、来源非空的观测"
            )
        matching_columns[display_name] = compatible[0]

    data_block = raw.iloc[6:, :].dropna(how="all")
    dates = pd.to_datetime(data_block.iloc[:, 0], errors="coerce")
    if dates.isna().any():
        row_number = int(dates[dates.isna()].index[0]) + 1
        raise ValueError(f"sheet“{DED_SHEET}”第{row_number}行日期无效")
    if dates.duplicated().any():
        raise ValueError(f"sheet“{DED_SHEET}”包含重复日期")

    series_map: dict[str, pd.Series] = {}
    metadata: dict[str, SheetSeriesMetadata] = {}
    for display_name, column_index in matching_columns.items():
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
                f"sheet“{DED_SHEET}”指标“{display_name}”"
                f"第{row_number}行不是数值"
            )
        series = pd.Series(
            numeric.mask(numeric.eq(0)).to_numpy(),
            index=pd.DatetimeIndex(dates),
            name=display_name,
        ).dropna().sort_index()
        if series.empty:
            raise ValueError(f"指标“{display_name}”没有非零有效观测")
        series_map[display_name] = series
        metadata[display_name] = SheetSeriesMetadata(
            display_name=display_name,
            indicator_name=normalize_indicator_name(
                raw.iloc[1, column_index]
            ),
            frequency=optional_text(raw.iloc[2, column_index]),
            unit=optional_text(raw.iloc[3, column_index]),
            source=_clean_source(optional_text(raw.iloc[4, column_index])),
            updated_at=format_updated_at(raw.iloc[5, column_index]),
            sheet_name=DED_SHEET,
        )

    ordered_names = [display_name for display_name, _ in DED_INDICATORS]
    frame = pd.concat(
        [series_map[name] for name in ordered_names],
        axis=1,
        sort=False,
    ).sort_index()
    return frame, metadata


def build_ded_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制当月新发执照数的月度柱状图（窗口 [last_month-36, last_month]，单序列无图例）。"""

    display_values = within_month_window(
        values,
        first_month=last_month - 36,
        last_month=last_month,
    )
    if display_values[LICENCES_DISPLAY].dropna().empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    frame = display_values[[LICENCES_DISPLAY]].dropna(how="all")
    axis_units = {LICENCES_DISPLAY: "张"}
    if units is not None:
        axis_units.update(units)
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        bar_series=[LICENCES_DISPLAY],
        bar_face_color=GRAY,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "ALLOWED_UNITS",
    "DED_INDICATORS",
    "DED_SHEET",
    "DedData",
    "ENTERPRISES_DISPLAY",
    "ENTERPRISES_INDICATOR",
    "LICENCES_DISPLAY",
    "LICENCES_INDICATOR",
    "build_ded_figure",
    "load_ded_data",
]
