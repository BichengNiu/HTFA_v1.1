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

WORK_DUBAI_LABEL = "搜索“在迪拜工作”（左轴）"
WORK_UAE_LABEL = "搜索“在阿联酋工作”（左轴）"
VISA_UAE_LABEL = "搜索“阿联酋签证”（右轴）"

LEFT_SERIES = (
    (WORK_DUBAI_COLUMN, WORK_DUBAI_LABEL, "#000000", "-"),
    (WORK_UAE_COLUMN, WORK_UAE_LABEL, "#1F4E79", "--"),
)
RIGHT_SERIES = (VISA_UAE_COLUMN, VISA_UAE_LABEL, "#B8BDC6", "-.")

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


def build_search_index_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """绘制工作与签证搜索指数，左轴工作搜索、右轴签证搜索。"""

    display_values = display_search_index_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    figure, left_axis = _new_ts_figure_axis()
    for column, label, color, linestyle in LEFT_SERIES:
        left_axis.plot(
            _smooth_series(display_values[column]),
            color=color,
            linewidth=2.2,
            linestyle=linestyle,
            label=label,
            zorder=3,
        )
    left_axis.set_ylabel("搜索指数", fontsize=12)
    left_axis.grid(axis="y", color="#D1D5DB", linewidth=0.7, zorder=0)
    left_axis.tick_params(
        axis="y",
        left=True,
        labelleft=True,
        right=False,
        labelright=False,
    )

    right_axis = left_axis.twinx()
    right_column, right_label, right_color, right_linestyle = RIGHT_SERIES
    right_axis.plot(
        _smooth_series(display_values[right_column]),
        color=right_color,
        linewidth=2.2,
        linestyle=right_linestyle,
        label=right_label,
        zorder=3,
    )
    right_axis.set_ylabel("搜索指数", fontsize=12)
    right_axis.grid(False)
    right_axis.tick_params(
        axis="y",
        left=False,
        labelleft=False,
        right=True,
        labelright=True,
    )

    right_axis.patch.set_visible(False)
    right_axis.set_zorder(1)
    left_axis.set_zorder(2)
    left_axis.patch.set_visible(False)

    left_axis.set_title(
        title,
        fontsize=14,
        pad=14,
        fontfamily=CHINESE_FONT_FAMILY,
    )
    left_axis.xaxis.grid(False)
    for spine_name in ("top", "bottom", "left"):
        spine = left_axis.spines[spine_name]
        spine.set_visible(True)
        spine.set_color("#6B7280")
        spine.set_linewidth(0.9)
    left_axis.spines["left"].set_color("#000000")
    left_axis.spines["right"].set_visible(False)
    right_axis.spines["right"].set_visible(True)
    right_axis.spines["right"].set_color("#000000")
    right_axis.spines["right"].set_linewidth(0.9)
    right_axis.spines["top"].set_visible(False)
    right_axis.spines["bottom"].set_visible(False)
    right_axis.spines["left"].set_visible(False)
    _apply_strict_month_ticks(left_axis, display_values.index)

    handles = [
        Line2D([0], [0], color=color, linewidth=2.2, linestyle=linestyle, label=label)
        for _, label, color, linestyle in LEFT_SERIES
    ]
    handles.append(
        Line2D(
            [0],
            [0],
            color=right_color,
            linewidth=2.2,
            linestyle=right_linestyle,
            label=right_label,
        )
    )
    figure.legend(
        handles=handles,
        labels=[label for _, label, *_ in LEFT_SERIES] + [right_label],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.115),
        frameon=False,
        prop={"family": CHINESE_FONT_FAMILY[0], "size": 10},
        ncol=len(handles),
    )
    _finish_dual_axis_figure(figure, top=0.90, right=0.88)
    _add_source_note(figure, source_text)
    return figure


__all__ = [
    "LEFT_SERIES",
    "RIGHT_SERIES",
    "SEARCH_CSV_RELATIVE",
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