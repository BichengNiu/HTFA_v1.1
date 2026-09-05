"""从本地谷歌趋势月度工作搜索热度绘制双轴折线图。"""

from __future__ import annotations

from typing import Any

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series
from scipy.signal import savgol_filter

from htfa.monitoring.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from htfa.monitoring.uae.sheet_reader import open_uae_workbook, parse_target_sheet

SMOOTH_WINDOW = 7
SMOOTH_POLYORDER = 2

SEARCH_SHEET = "月度_工作搜索热度"

WORK_DUBAI_COLUMN = "work in dubai"
WORK_UAE_COLUMN = "work in uae"

SEARCH_INDICATORS = (
    (WORK_DUBAI_COLUMN, "阿联酋:Google搜索热度(work in dubai)"),
    (WORK_UAE_COLUMN, "阿联酋:Google搜索热度(work in uae)"),
)

WORK_DUBAI_LABEL = "搜索“在迪拜工作”"
WORK_UAE_LABEL = "搜索“在阿联酋工作”"

SEARCH_SERIES = (
    (WORK_DUBAI_COLUMN, WORK_DUBAI_LABEL),
    (WORK_UAE_COLUMN, WORK_UAE_LABEL),
)

START_YEAR = 2023
SOURCE_TEXT = "谷歌趋势"


def load_search_index_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> pd.DataFrame:
    """从工作簿的 ``月度_工作搜索热度`` 读取谷歌趋势序列。"""

    with open_uae_workbook(file_input, file_name=file_name) as (excel_file, _):
        values, _ = parse_target_sheet(
            excel_file,
            sheet_name=SEARCH_SHEET,
            targets=SEARCH_INDICATORS,
            allowed_frequencies={"月", "月度"},
            expected_unit="指数",
            zero_is_missing=False,
        )
    values = values.sort_index()
    values.index = pd.DatetimeIndex(values.index).normalize()
    return values


def display_search_index_values(values: pd.DataFrame) -> pd.DataFrame:
    """返回从指定年份起的工作搜索热度观测。"""

    return values.loc[values.index >= pd.Timestamp(START_YEAR, 1, 1)]


def _smooth_series(series: pd.Series) -> pd.Series:
    """用 Savitzky-Golay 平滑曲线，接近谷歌趋势的展示效果。"""

    values = series.dropna().astype(float)
    window = min(SMOOTH_WINDOW, len(values))
    if window % 2 == 0:
        window -= 1
    if window < 3 or len(values) < window:
        return series
    return pd.Series(
        savgol_filter(values.to_numpy(), window, SMOOTH_POLYORDER),
        index=values.index,
    )


def _standardize_series(series: pd.Series) -> pd.Series:
    """Z-score 标准化，使不同关键词热度可在同一坐标轴上比较。"""

    values = series.dropna().astype(float)
    std = values.std()
    if values.empty or pd.isna(std) or std == 0:
        return values
    return (values - values.mean()) / std


def build_search_index_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """两个工作搜索关键词经 Z-score 标准化后在同一坐标轴展示。"""

    display_values = display_search_index_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    frame = pd.DataFrame(
        {
            label: _standardize_series(_smooth_series(display_values[column]))
            for column, label in SEARCH_SERIES
        }
    )
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units={label: "标准化指数" for _, label in SEARCH_SERIES},
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "SEARCH_INDICATORS",
    "SEARCH_SERIES",
    "SEARCH_SHEET",
    "SMOOTH_POLYORDER",
    "SMOOTH_WINDOW",
    "SOURCE_TEXT",
    "START_YEAR",
    "WORK_DUBAI_COLUMN",
    "WORK_DUBAI_LABEL",
    "WORK_UAE_COLUMN",
    "WORK_UAE_LABEL",
    "build_search_index_figure",
    "display_search_index_values",
    "load_search_index_data",
]
