"""从阿联酋工作簿读取 MEsteel 钢材月度报价并对缺失月做多项式插补。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.oil.alignment import within_month_window
from dashboard.analysis.uae.oil.charts import (
    CHINESE_FONT_FAMILY,
    _add_source_note,
    _apply_strict_month_ticks,
    _finish_dual_axis_figure,
    _new_ts_figure_axis,
    _normalize_ts_axis,
)
from dashboard.analysis.uae.oil.data import (
    OilSeriesMetadata,
    _parse_target_sheet,
    _workbook_buffer,
)


STEEL_SHEET = "月度_MEsteel"
REBAR_LABEL = "螺纹钢"
EN_BEAMS_LABEL = "EN及UB/UC型钢梁和槽钢"
REBAR_INDICATOR = "阿联酋:钢材进口报价:螺纹钢:CFR/CPT:区间中值"
EN_BEAMS_INDICATOR = "阿联酋:钢材进口报价:EN及UB/UC型钢梁和槽钢:CFR/CPT:区间中值"
STEEL_INDICATORS: tuple[tuple[str, str], ...] = (
    (REBAR_LABEL, REBAR_INDICATOR),
    (EN_BEAMS_LABEL, EN_BEAMS_INDICATOR),
)

REBAR_COLOR = "#000000"
EN_BEAMS_COLOR = "#1F4E79"
STEEL_LINE_SPECS = (
    (REBAR_LABEL, REBAR_LABEL, REBAR_COLOR, "-"),
    (EN_BEAMS_LABEL, EN_BEAMS_LABEL, EN_BEAMS_COLOR, "--"),
)

POLYNOMIAL_ORDER = 3
DISPLAY_MONTHS = 37


@dataclass(frozen=True)
class SteelData:
    """两条 MEsteel 钢材报价月度序列及来源信息。"""

    values: pd.DataFrame
    metadata: dict[str, OilSeriesMetadata]
    source_name: str


def load_steel_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> SteelData:
    """只读取 ``月度_MEsteel`` 的螺纹钢与 EN及UB/UC 型钢梁和槽钢报价。"""

    buffer, source_name = _workbook_buffer(file_input, file_name=file_name)
    excel_file = pd.ExcelFile(buffer)
    try:
        values, metadata = _parse_target_sheet(
            excel_file,
            sheet_name=STEEL_SHEET,
            targets=STEEL_INDICATORS,
            allowed_frequencies={"月", "月度"},
            expected_unit="美元/吨",
        )
    finally:
        excel_file.close()

    return SteelData(
        values=values,
        metadata=metadata,
        source_name=source_name,
    )


def interpolate_steel_values(values: pd.DataFrame) -> pd.DataFrame:
    """把两条序列对齐到完整月份网格并用多项式补齐缺失月。"""

    monthly = values.copy().sort_index()
    if monthly.empty:
        raise ValueError("钢材价格没有可绘制的有效数据")

    periods = pd.PeriodIndex(pd.DatetimeIndex(monthly.index), freq="M")
    complete = pd.period_range(periods.min(), periods.max(), freq="M")
    full = monthly.reindex(complete.to_timestamp(how="end").normalize())

    numeric = full.copy()
    numeric.index = pd.RangeIndex(len(full.index))
    interpolated = numeric.interpolate(
        method="spline",
        order=POLYNOMIAL_ORDER,
        limit_direction="both",
    )
    interpolated.index = full.index
    return interpolated


def display_steel_values(values: pd.DataFrame) -> pd.DataFrame:
    """返回最近展示窗口内、缺失月已做多项式插补的报价。"""

    interpolated = interpolate_steel_values(values)
    last_month = pd.Timestamp(interpolated.index[-1]).to_period("M")
    return within_month_window(
        interpolated,
        first_month=last_month - (DISPLAY_MONTHS - 1),
        last_month=last_month,
    )


def build_steel_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """绘制螺纹钢与 EN及UB/UC 型钢梁和槽钢的月度报价线图。"""

    display_values = display_steel_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    figure, axis = _new_ts_figure_axis()
    for index, (column, label, color, linestyle) in enumerate(STEEL_LINE_SPECS):
        figure, returned_axis = plot_series(
            display_values[column].rename(label),
            title=None,
            xtitle="",
            ytitle="美元/吨",
            colors=[color],
            linewidth=2.2,
            markersize=0,
            max_ticks=8,
            freq="month",
            show_legend=False,
            note=None,
            grid=index == len(STEEL_LINE_SPECS) - 1,
            ax=axis,
        )
        axis = _normalize_ts_axis(returned_axis)
        axis.get_lines()[-1].set_linestyle(linestyle)

    axis.set_title(title, fontsize=14, pad=14)
    axis.xaxis.grid(False)
    axis.set_ylabel("美元/吨", fontsize=12)
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color("#6B7280")
        spine.set_linewidth(0.9)
    _apply_strict_month_ticks(axis, display_values.index)
    figure.legend(
        handles=axis.get_lines()[: len(STEEL_LINE_SPECS)],
        labels=[spec[0] for spec in STEEL_LINE_SPECS],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.115),
        frameon=False,
        prop={"family": CHINESE_FONT_FAMILY[0], "size": 10},
        ncol=len(STEEL_LINE_SPECS),
    )
    _finish_dual_axis_figure(figure, top=0.90)
    _add_source_note(figure, source_text)
    return figure


__all__ = [
    "EN_BEAMS_INDICATOR",
    "EN_BEAMS_LABEL",
    "REBAR_INDICATOR",
    "REBAR_LABEL",
    "STEEL_INDICATORS",
    "STEEL_LINE_SPECS",
    "STEEL_SHEET",
    "SteelData",
    "build_steel_figure",
    "display_steel_values",
    "interpolate_steel_values",
    "load_steel_data",
]