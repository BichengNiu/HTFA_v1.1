"""从本地谷歌趋势月度工作搜索热度绘制双轴折线图。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series
from scipy.signal import savgol_filter

from dashboard.analysis.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)

SMOOTH_WINDOW = 7
SMOOTH_POLYORDER = 2

SEARCH_CSV_RELATIVE = "data/UAE/工作搜索热度.csv"

TIME_COLUMN = "Time"
WORK_DUBAI_COLUMN = "work in dubai"
WORK_UAE_COLUMN = "work in uae"

WORK_DUBAI_LABEL = "搜索“在迪拜工作”"
WORK_UAE_LABEL = "搜索“在阿联酋工作”"

SEARCH_SERIES = (
    (WORK_DUBAI_COLUMN, WORK_DUBAI_LABEL),
    (WORK_UAE_COLUMN, WORK_UAE_LABEL),
)

START_YEAR = 2023
SOURCE_TEXT = "Google 趋势"


def _search_csv_path() -> Path:
    """返回工作搜索热度 CSV 的绝对路径。"""

    project_root = Path(__file__).resolve().parents[4]
    return project_root / SEARCH_CSV_RELATIVE


def load_search_index_data() -> pd.DataFrame:
    """读取谷歌趋势月度工作搜索热度，索引为时间戳。"""

    path = _search_csv_path()
    if not path.exists():
        raise FileNotFoundError(f"缺少谷歌搜索热度数据文件：{path}")
    frame = pd.read_csv(path)
    frame[TIME_COLUMN] = pd.to_datetime(frame[TIME_COLUMN])
    values = frame.set_index(TIME_COLUMN)[
        [WORK_DUBAI_COLUMN, WORK_UAE_COLUMN]
    ].sort_index()
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
        ytitle="标准化搜索指数",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "SEARCH_CSV_RELATIVE",
    "SEARCH_SERIES",
    "SMOOTH_POLYORDER",
    "SMOOTH_WINDOW",
    "SOURCE_TEXT",
    "START_YEAR",
    "TIME_COLUMN",
    "WORK_DUBAI_COLUMN",
    "WORK_DUBAI_LABEL",
    "WORK_UAE_COLUMN",
    "WORK_UAE_LABEL",
    "build_search_index_figure",
    "display_search_index_values",
    "load_search_index_data",
]