"""从本地谷歌趋势月度工作搜索热度绘制双轴折线图。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from scipy.signal import savgol_filter

from dashboard.analysis.uae.oil.charts import (
    CHINESE_FONT_FAMILY,
    _add_source_note,
    _apply_strict_month_ticks,
    _finish_dual_axis_figure,
    _new_ts_figure_axis,
)

SMOOTH_WINDOW = 7
SMOOTH_POLYORDER = 2

SEARCH_CSV_RELATIVE = "data/employment/工作搜索热度.csv"

TIME_COLUMN = "Time"
WORK_DUBAI_COLUMN = "work in dubai"
WORK_UAE_COLUMN = "work in uae"
VISA_UAE_COLUMN = "visa uae"

WORK_DUBAI_LABEL = "搜索“在迪拜工作”"
WORK_UAE_LABEL = "搜索“在阿联酋工作”"
VISA_UAE_LABEL = "搜索“阿联酋签证”"

SEARCH_SERIES = (
    (WORK_DUBAI_COLUMN, WORK_DUBAI_LABEL, "#000000", "-"),
    (WORK_UAE_COLUMN, WORK_UAE_LABEL, "#1F4E79", "--"),
    (VISA_UAE_COLUMN, VISA_UAE_LABEL, "#6B7280", "-."),
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
        [WORK_DUBAI_COLUMN, WORK_UAE_COLUMN, VISA_UAE_COLUMN]
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
    """三个关键词搜索热度经 Z-score 标准化后在同一坐标轴展示。"""

    display_values = display_search_index_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    figure, axis = _new_ts_figure_axis()
    for column, label, color, linestyle in SEARCH_SERIES:
        axis.plot(
            _standardize_series(_smooth_series(display_values[column])),
            color=color,
            linewidth=2.2,
            linestyle=linestyle,
            label=label,
            zorder=3,
        )
    axis.axhline(0, color="#9CA3AF", linewidth=0.8, linestyle=":", zorder=1)
    axis.set_ylabel("标准化搜索指数", fontsize=12)
    axis.grid(axis="y", color="#D1D5DB", linewidth=0.7, zorder=0)
    axis.tick_params(
        axis="y",
        left=True,
        labelleft=True,
        right=False,
        labelright=False,
    )
    axis.set_title(
        title,
        fontsize=14,
        pad=14,
        fontfamily=CHINESE_FONT_FAMILY,
    )
    axis.xaxis.grid(False)
    for spine_name in ("top", "bottom", "left", "right"):
        spine = axis.spines[spine_name]
        spine.set_visible(True)
        spine.set_color("#6B7280")
        spine.set_linewidth(0.9)
    axis.spines["left"].set_color("#000000")
    _apply_strict_month_ticks(axis, display_values.index)

    handles = [
        Line2D([0], [0], color=color, linewidth=2.2, linestyle=linestyle, label=label)
        for _, label, color, linestyle in SEARCH_SERIES
    ]
    figure.legend(
        handles=handles,
        labels=[label for _, label, *_ in SEARCH_SERIES],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.115),
        frameon=False,
        prop={"family": CHINESE_FONT_FAMILY[0], "size": 10},
        ncol=len(handles),
    )
    _finish_dual_axis_figure(figure, top=0.90)
    _add_source_note(figure, source_text)
    return figure


__all__ = [
    "SEARCH_CSV_RELATIVE",
    "SEARCH_SERIES",
    "SMOOTH_POLYORDER",
    "SMOOTH_WINDOW",
    "SOURCE_TEXT",
    "START_YEAR",
    "TIME_COLUMN",
    "VISA_UAE_COLUMN",
    "VISA_UAE_LABEL",
    "WORK_DUBAI_COLUMN",
    "WORK_DUBAI_LABEL",
    "WORK_UAE_COLUMN",
    "WORK_UAE_LABEL",
    "build_search_index_figure",
    "display_search_index_values",
    "load_search_index_data",
]