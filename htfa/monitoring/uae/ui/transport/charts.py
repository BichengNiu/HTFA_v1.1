from __future__ import annotations
from collections.abc import Mapping
import re
import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series
from htfa.monitoring.uae.ui.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
)
from htfa.monitoring.uae.processing.sources import source_note
from htfa.monitoring.uae.processing.transport.charts import _windowed


def _legend_label_without_unit(label: str) -> str:
    """删除技术变量名中的单位、下划线和“合计”字样。"""
    without_unit = re.sub("(?:\\([^()]*\\)|（[^（）]*）)$", "", label)
    return without_unit.replace("_", "").replace("合计", "").replace("↔", "—").strip()


def normalize_legend_labels(
    legend_labels: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    if legend_labels is None:
        return None
    return tuple((_legend_label_without_unit(label) for label in legend_labels))


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
        设置序列显示名；长度必须与 ``columns`` 一致，双轴图自动追加轴标记。
    """
    display = _windowed(values, last_month)
    missing = [column for column in columns if column not in display]
    if missing or display[list(columns)].dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效观测")
    frame = display[list(columns)].dropna(how="all")
    series_labels = normalize_legend_labels(legend_labels)
    figure, returned_axis = plot_series(
        frame,
        labels=series_labels,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
        units={label: unit for label in series_labels or columns},
    )
    axis = normalize_ts_axis(returned_axis)
    axis.set_ylim(bottom=0)
    if unit == "百万吨":
        axis.ticklabel_format(style="plain", axis="y", useOffset=False)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


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
        设置序列显示名；长度必须与 ``columns`` 一致，图例自动追加轴标记。
    """
    if not left_columns or not right_columns:
        raise ValueError("双纵轴必须分别指定左右轴序列")
    if set(left_columns).intersection(right_columns):
        raise ValueError("双纵轴序列不能同时属于左右轴")
    if set(columns) != set(left_columns).union(right_columns):
        raise ValueError("双纵轴序列必须覆盖全部绘图列")
    if any((column not in units for column in columns)):
        raise ValueError("双纵轴序列缺少单位")
    display = _windowed(values, last_month)
    missing = [column for column in columns if column not in display]
    if missing or display[list(columns)].dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效观测")
    frame = display[list(columns)].dropna(how="all")
    series_labels = normalize_legend_labels(legend_labels)
    display_names = columns if series_labels is None else series_labels
    axis_groups = {
        label: "left" if column in left_columns else "right"
        for column, label in zip(columns, display_names, strict=True)
    }
    figure, returned_axis = plot_series(
        frame,
        labels=series_labels,
        facet=False,
        axis_groups=axis_groups,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
        units={
            label: units[column]
            for column, label in zip(columns, display_names, strict=True)
        },
    )
    axis = normalize_ts_axis(returned_axis)
    for chart_axis in (axis, axis.right_ax):
        chart_axis.set_ylim(bottom=0)
        chart_axis.ticklabel_format(style="plain", axis="y", useOffset=False)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure
