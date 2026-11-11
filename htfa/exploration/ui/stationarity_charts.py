"""探索页面的时间序列及相关图绘制。"""
from __future__ import annotations
from typing import Any
from matplotlib.ticker import MaxNLocator
from htfa.exploration.processing.validation import validate_real_series as _validate_numeric_series
_GRID_LINE_STYLES = {
    "solid": "-",
    "dashed": "--",
    "dotted": ":",
    "dashdot": "-.",
}



import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from Ts.TsPlots import plot_acf, plot_pacf, plot_series
from htfa.ui_shared.matplotlib_compat import matplotlib_date_compatibility
from htfa.exploration.processing.analysis.stationarity import resolve_correlation_lags


def create_time_series_figure(
    series: pd.Series,
    *,
    title: str | None = None,
    x_title: str = "时间",
    y_title: str | None = None,
    line_width: float = 3,
    marker_size: float = 0,
    max_ticks: int = 12,
    y_tick_count: int = 8,
    x_start=None,
    y_start: float | None = None,
    grid_mode: str = "both",
    grid_line_style: str = "solid",
    grid: bool | None = None,
    ymin: float | None = None,
):
    """使用 ``Ts.TsPlots.plot_series`` 绘制时间序列。"""
    values = _validate_numeric_series(series)
    if y_start is None:
        y_start = ymin
    if grid is not None:
        grid_mode = "both" if grid else "none"
    with matplotlib_date_compatibility():
        figure, axis = plot_series(
            values,
            title=title,
            xtitle=x_title,
            ytitle=y_title or str(series.name or "数值"),
            linewidth=line_width,
            markersize=marker_size,
            max_ticks=max_ticks,
            grid=False,
            ymin=y_start,
            show_legend=False,
        )
        _apply_axis_options(
            axis,
            x_start=x_start,
            y_start=y_start,
            x_tick_count=max_ticks,
            y_tick_count=y_tick_count,
            grid_mode=grid_mode,
            grid_line_style=grid_line_style,
            date_x_axis=isinstance(values.index, pd.DatetimeIndex),
        )
    return figure


def _apply_axis_options(
    axis,
    *,
    x_start=None,
    y_start: float | None = None,
    x_tick_count: int = 12,
    y_tick_count: int = 8,
    grid_mode: str = "both",
    grid_line_style: str = "solid",
    date_x_axis: bool = False,
) -> None:
    """将坐标轴范围、刻度数量和网格方向统一应用到单个坐标轴。"""
    if x_start is not None:
        axis.set_xlim(left=x_start)
    if y_start is not None:
        axis.set_ylim(bottom=y_start)
    if not date_x_axis:
        axis.xaxis.set_major_locator(MaxNLocator(nbins=max(2, int(x_tick_count))))
    axis.yaxis.set_major_locator(MaxNLocator(nbins=max(2, int(y_tick_count))))
    try:
        line_style = _GRID_LINE_STYLES[grid_line_style]
    except KeyError as exc:
        raise ValueError(f"未知网格线型: {grid_line_style}") from exc
    axis.grid(False)
    if grid_mode == "horizontal":
        axis.yaxis.grid(True, linestyle=line_style)
    elif grid_mode == "vertical":
        axis.xaxis.grid(True, linestyle=line_style)
    elif grid_mode == "both":
        axis.grid(True, linestyle=line_style)
    elif grid_mode != "none":
        raise ValueError(f"未知网格方向: {grid_mode}")


def create_correlogram_figure(
    series: pd.Series,
    *,
    nlags: int | None = None,
    alpha: float = 0.05,
    title_prefix: str | None = None,
    include_acf: bool = True,
    include_pacf: bool = True,
    acf_title: str | None = None,
    pacf_title: str | None = None,
    acf_x_title: str = "滞后期数",
    acf_y_title: str = "ACF值",
    pacf_x_title: str = "滞后期数",
    pacf_y_title: str = "PACF值",
    max_ticks: int = 12,
    y_tick_count: int = 8,
    x_start: float | None = 0,
    y_start: float | None = None,
    grid_mode: str = "both",
    grid_line_style: str = "solid",
    grid: bool | None = None,
    pacf_method: str = "ywm",
):
    """使用 ``Ts`` 绘制同一序列的 ACF 和 PACF。"""
    if not include_acf and not include_pacf:
        raise ValueError("至少选择绘制 ACF 或 PACF")
    values = _validate_numeric_series(series).dropna()
    if grid is not None:
        grid_mode = "both" if grid else "none"
    resolved_lags, _ = resolve_correlation_lags(values, nlags)
    if values.nunique() <= 1:
        raise ValueError("常数序列无法计算 ACF/PACF")

    prefix = f"{title_prefix} · " if title_prefix else ""
    plotters = []
    if include_acf:
        plotters.append(("ACF", plot_acf))
    if include_pacf:
        plotters.append(("PACF", plot_pacf))
    figure, axes = plt.subplots(
        1,
        len(plotters),
        figsize=(6.5 * len(plotters), 4.5),
        squeeze=False,
    )
    try:
        for axis, (label, plotter) in zip(axes.flat, plotters, strict=True):
            plot_kwargs = {
                "nlags": resolved_lags,
                "alpha": alpha,
                "title": (
                    acf_title if label == "ACF" and acf_title is not None
                    else pacf_title if label == "PACF" and pacf_title is not None
                    else f"{prefix}{label}"
                ),
                "xtitle": acf_x_title if label == "ACF" else pacf_x_title,
                "ytitle": acf_y_title if label == "ACF" else pacf_y_title,
                "max_ticks": max_ticks,
                "grid": False,
                "ax": axis,
            }
            if label == "ACF":
                plot_kwargs["zero_lag"] = False
            else:
                plot_kwargs["method"] = pacf_method
            plotter(
                values,
                **plot_kwargs,
            )
            _apply_axis_options(
                axis,
                x_start=x_start,
                y_start=y_start,
                x_tick_count=max_ticks,
                y_tick_count=y_tick_count,
                grid_mode=grid_mode,
                grid_line_style=grid_line_style,
            )
        figure.tight_layout()
        return figure
    except Exception:
        plt.close(figure)
        raise
