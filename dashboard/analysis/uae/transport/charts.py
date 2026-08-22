"""交通物流月度图：UAE 港口货量与霍尔木兹过境次数（Ts 默认模板）。

左图为 UAE 港口进口/出口总量及油轮进口/出口量四条吨位线；右图为霍尔木兹
过境总次数及油轮过境次数两条艘次线。

两图按板块锚定月往前 36 个月，红色虚线为 2026 年 3 月美伊战争起始基准线
（模板参考线默认色）。图例/图注由模板托管；字体覆盖为微软雅黑（项目豁免）。
"""

from __future__ import annotations

from collections.abc import Mapping
import re

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.oil.alignment import within_month_window
from dashboard.analysis.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
UAE_PORT_VOLUME_TITLE = "阿联酋港口进出口货运量"
HORMUZ_CALLS_TITLE = "霍尔木兹海峡过境次数"
DUBAI_AIR_AWBS_TITLE = "迪拜航空货运进出口运单数"
DUBAI_AIR_TOTAL_TITLE = "迪拜航空货运进出口总量"
DUBAI_AIR_CARGO_TITLE = "迪拜航空货运进出口运单数与总量"
US_UAE_AIR_TITLE = "美国↔阿联酋航空运输"


def _legend_label_without_unit(label: str) -> str:
    """删除图例变量名末尾的括号单位，保留纵轴单位显示。"""

    return re.sub(r"(?:\([^()]*\)|（[^（）]*）)$", "", label).rstrip()


def _normalize_legend_labels(
    legend_labels: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if legend_labels is None:
        return None
    return tuple(_legend_label_without_unit(label) for label in legend_labels)


def _windowed(
    frame: pd.DataFrame,
    last_month: pd.Period,
) -> pd.DataFrame:
    return within_month_window(
        frame,
        first_month=last_month - 36,
        last_month=last_month,
    ).dropna(how="all")


def build_multi_series_figure(
    values: pd.DataFrame,
    *,
    columns: tuple[str, ...],
    title: str,
    unit: str,
    source_text: str,
    last_month: pd.Period,
    legend_labels: tuple[str, ...] | None = None,
) -> Figure:
    """按交通物流现有模板绘制一张同单位多序列图。

    Parameters
    ----------
    values : pandas.DataFrame
        已按图表展示口径准备好的月度序列。
    columns : tuple[str, ...]
        需要绘制的列名，顺序决定图例顺序。
    title : str
        图表标题。
    unit : str
        y 轴单位。
    source_text : str
        图注中的数据来源文字。
    last_month : pandas.Period
        窗口右端月份。
    legend_labels : tuple[str, ...] or None, optional
        覆盖图例文字；长度必须与 ``columns`` 一致。
    """

    display = _windowed(values, last_month)
    missing = [column for column in columns if column not in display]
    if missing or display[list(columns)].dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效观测")

    frame = display[list(columns)].dropna(how="all")
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        legend_labels=_normalize_legend_labels(legend_labels),
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units={column: unit for column in columns},
    )
    axis = normalize_ts_axis(returned_axis)
    axis.set_ylim(bottom=0)
    if unit == "百万吨":
        axis.ticklabel_format(style="plain", axis="y", useOffset=False)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


def build_single_series_figure(
    values: pd.DataFrame,
    *,
    column: str,
    title: str,
    unit: str,
    source_text: str,
    last_month: pd.Period,
) -> Figure:
    """按交通物流现有模板绘制一张单序列图。"""

    return build_multi_series_figure(
        values,
        columns=(column,),
        title=title,
        unit=unit,
        source_text=source_text,
        last_month=last_month,
    )


def build_dual_axis_figure(
    values: pd.DataFrame,
    *,
    columns: tuple[str, ...],
    left_columns: tuple[str, ...],
    right_columns: tuple[str, ...],
    title: str,
    units: Mapping[str, str],
    source_text: str,
    last_month: pd.Period,
    legend_labels: tuple[str, ...] | None = None,
) -> Figure:
    """按交通物流现有模板绘制一张双纵轴多序列图。

    Parameters
    ----------
    values : pandas.DataFrame
        已按图表展示口径准备好的月度序列。
    columns : tuple[str, ...]
        需要绘制的列名，顺序决定图例顺序。
    left_columns : tuple[str, ...]
        使用左侧纵轴的列名。
    right_columns : tuple[str, ...]
        使用右侧纵轴的列名。
    title : str
        图表标题。
    units : Mapping[str, str]
        每条序列对应的单位。
    source_text : str
        图注中的数据来源文字。
    last_month : pandas.Period
        窗口右端月份。
    legend_labels : tuple[str, ...] or None, optional
        覆盖图例文字；长度必须与 ``columns`` 一致。
    """

    if set(left_columns).intersection(right_columns):
        raise ValueError("双纵轴序列不能同时属于左右轴")
    if set(columns) != set(left_columns).union(right_columns):
        raise ValueError("双纵轴序列必须覆盖全部绘图列")
    if any(column not in units for column in columns):
        raise ValueError("双纵轴序列缺少单位")

    display = _windowed(values, last_month)
    missing = [column for column in columns if column not in display]
    if missing or display[list(columns)].dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效观测")

    frame = display[list(columns)].dropna(how="all")
    axis_groups = {
        column: "left" if column in left_columns else "right"
        for column in columns
    }
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups=axis_groups,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        legend_labels=_normalize_legend_labels(legend_labels),
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=dict(units),
    )
    axis = normalize_ts_axis(returned_axis)
    right_axis = getattr(axis, "right_ax", None)
    for chart_axis in (axis, right_axis):
        if chart_axis is not None:
            chart_axis.set_ylim(bottom=0)
            chart_axis.ticklabel_format(style="plain", axis="y", useOffset=False)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "HORMUZ_CALLS_TITLE",
    "UAE_PORT_VOLUME_TITLE",
    "DUBAI_AIR_AWBS_TITLE",
    "DUBAI_AIR_TOTAL_TITLE",
    "DUBAI_AIR_CARGO_TITLE",
    "US_UAE_AIR_TITLE",
    "build_dual_axis_figure",
    "build_multi_series_figure",
    "build_single_series_figure",
]
