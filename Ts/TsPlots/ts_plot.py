"""Reusable plotting utilities for time series visualization.

The main entry point is :func:`plot_series`, which draws an arbitrary number
of series. Styling cycles per series: even-indexed series are drawn as solid
lines with filled circles, odd-indexed series as dashed lines with hollow
circles, with colors from a colorblind-friendly palette.

Accepted inputs
---------------
- pandas DataFrame : each column becomes a series. The time axis is the index
  by default, or a column named via ``x``.
- pandas Series    : a single series indexed by its index.
- dict             : ``{label: values}`` for multiple named series.
- 2D array         : each column becomes a series.
- 1D array         : a single series.

Examples
--------
>>> import numpy as np, pandas as pd
>>> from Ts.TsPlots import plot_series
>>> # DataFrame, index as time
>>> df = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]}, index=[2000, 2001, 2002])
>>> fig, ax = plot_series(df)
>>> # DataFrame, a column as the time variable
>>> df2 = pd.DataFrame({"year": [2000, 2001, 2002], "a": [1, 2, 3], "b": [3, 2, 1]})
>>> fig, ax = plot_series(df2, x="year")
>>> # dict of named series
>>> fig, ax = plot_series({"s1": [1, 2, 3], "s2": [3, 2, 1]}, x=[1, 2, 3])
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator, FuncFormatter
import numpy as np
import pandas as pd

from .style import (
    _ensure_fonts,
    _FigureContext,
    _resolve_colors,
    _validate_positive_step,
    DEFAULT_PALETTE,
    DEFAULT_LINESTYLES,
    DEFAULT_MARKERS,
    AXIS_LABEL_FONTSIZE,
    draw_shade,
    draw_vlines,
)


_VALID_FREQS = {"day", "week", "month", "quarter", "year"}


def _make_chinese_formatter(freq: str) -> FuncFormatter:
    """Return a FuncFormatter that renders datetime ticks in Chinese.

    Formats
    -------
    day     : XXXX年X月X日      e.g. 2026年6月27日
    week    : XXXX年X月第X周    e.g. 2026年6月第4周
    month   : XXXX年X月         e.g. 2026年6月
    quarter : XXXX年第X季度     e.g. 2026年第2季度
    year    : XXXX年             e.g. 2026年
    """
    if freq == "day":

        def _fmt(x, pos):
            dt = mdates.num2date(x)
            return f"{dt.year}年{dt.month}月{dt.day}日"

    elif freq == "week":

        def _fmt(x, pos):
            dt = mdates.num2date(x)
            week_of_month = (dt.day - 1) // 7 + 1
            return f"{dt.year}年{dt.month}月第{week_of_month}周"

    elif freq == "month":

        def _fmt(x, pos):
            dt = mdates.num2date(x)
            return f"{dt.year}年{dt.month}月"

    elif freq == "quarter":

        def _fmt(x, pos):
            dt = mdates.num2date(x)
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}年第{quarter}季度"

    elif freq == "year":

        def _fmt(x, pos):
            dt = mdates.num2date(x)
            return f"{dt.year}年"

    else:
        raise ValueError(
            f"freq={freq!r} is not valid. Choose from: "
            + ", ".join(sorted(_VALID_FREQS))
        )

    return FuncFormatter(_fmt)


def _apply_freq_ticks(ax, x_values, freq: str, max_ticks: int = 12) -> None:
    """Apply a matplotlib.dates locator/formatter for the given frequency.

    The locator interval is calculated from the data's date range and
    ``max_ticks`` so that at most ``max_ticks`` ticks are displayed.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x_values : array-like
        The x data (must be datetime-like for this function to have any effect).
    freq : str
        One of 'day', 'week', 'month', 'quarter', 'year'.
    max_ticks : int
        Upper bound on the number of ticks. Defaults to 12.
    """
    if freq not in _VALID_FREQS:
        raise ValueError(
            f"freq={freq!r} is not valid. Choose from: "
            + ", ".join(sorted(_VALID_FREQS))
        )

    x_dt = pd.DatetimeIndex(pd.to_datetime(x_values))
    d_min, d_max = x_dt.min(), x_dt.max()

    if freq == "day":
        n = max(1, (d_max - d_min).days + 1)
        interval = max(1, int(np.ceil(n / max_ticks)))
        locator = mdates.DayLocator(interval=interval)

    elif freq == "week":
        n = max(1, (d_max - d_min).days // 7 + 1)
        interval = max(1, int(np.ceil(n / max_ticks)))
        locator = mdates.WeekdayLocator(byweekday=mdates.MO, interval=interval)

    elif freq == "month":
        n = (d_max.year - d_min.year) * 12 + (d_max.month - d_min.month) + 1
        interval = max(1, int(np.ceil(n / max_ticks)))
        locator = mdates.MonthLocator(interval=interval)

    elif freq == "quarter":
        n_months = (d_max.year - d_min.year) * 12 + (d_max.month - d_min.month) + 1
        n = max(1, int(np.ceil(n_months / 3)))
        interval = max(1, int(np.ceil(n / max_ticks)))
        locator = mdates.MonthLocator(interval=3 * interval)

    elif freq == "year":
        n = max(1, d_max.year - d_min.year + 1)
        interval = max(1, int(np.ceil(n / max_ticks)))
        locator = mdates.YearLocator(base=interval)

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(_make_chinese_formatter(freq))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")


def _resolve_input(data, x, y) -> tuple[np.ndarray, dict, str]:
    """Normalize supported inputs into (x_values, series_dict, default_xlabel).

    series_dict maps label -> values, preserving order.
    """
    if isinstance(data, pd.DataFrame):
        if x is None:
            x_values = data.index.to_numpy()
            default_xlabel = data.index.name or "Time"
            cols = list(data.columns)
        elif isinstance(x, str):
            if x not in data.columns:
                raise KeyError(f"Column {x!r} not found in DataFrame.")
            x_values = data[x].to_numpy()
            default_xlabel = x
            cols = [c for c in data.columns if c != x]
        else:
            x_values = np.asarray(x)
            default_xlabel = "Time"
            cols = list(data.columns)

        if y is not None:
            cols = [y] if isinstance(y, str) else list(y)

        series = {str(c): data[c].to_numpy() for c in cols}
        return x_values, series, default_xlabel

    if isinstance(data, pd.Series):
        x_values = np.asarray(x) if x is not None else data.index.to_numpy()
        default_xlabel = "Time" if x is not None else (data.index.name or "Time")
        label = data.name if data.name is not None else "Series 1"
        return x_values, {str(label): data.to_numpy()}, default_xlabel

    if isinstance(data, dict):
        series = {str(k): np.asarray(v) for k, v in data.items()}
        first_len = len(next(iter(series.values())))
        x_values = np.asarray(x) if x is not None else np.arange(first_len)
        return x_values, series, "Time"

    arr = np.asarray(data)
    if arr.ndim == 1:
        x_values = np.asarray(x) if x is not None else np.arange(len(arr))
        return x_values, {"Series 1": arr}, "Time"
    if arr.ndim == 2:
        n_rows, n_cols = arr.shape
        x_values = np.asarray(x) if x is not None else np.arange(n_rows)
        series = {f"Series {i + 1}": arr[:, i] for i in range(n_cols)}
        return x_values, series, "Time"

    raise TypeError(f"Unsupported data type: {type(data)!r}")


def plot_series(
    data,
    x=None,
    y=None,
    *,
    labels=None,
    colors=None,
    title: str | None = None,
    xtitle: str | None = None,
    ytitle: str = "Value",
    linewidth: float = 3,
    markersize: float = 7,
    marker_edge_width: float = 2.5,
    xtick_step: int | None = None,
    max_ticks: int = 12,
    freq: str | None = None,
    ymin: float | None = None,
    show_legend: bool = True,
    legend_labels=None,
    legend_loc: str = "best",
    legend_bbox=None,
    title_loc: str = "center",
    title_pad: float = 12,
    title_position: str = "top",
    note: str | None = None,
    grid: bool = False,
    show_values: bool = False,
    value_decimals: int = 1,
    vlines=None,
    vline_color: str = "#d9534f",
    vline_linestyle: str = "--",
    vline_linewidth: float = 1.5,
    shade=None,
    shade_color: str = "#d0d0d0",
    shade_alpha: float = 0.3,
    ax=None,
    unit: str | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Plot an arbitrary number of time series with cycling styles.

    Styling cycles per series so that each added line differs in color, line
    style, and marker shape, keeping series distinguishable even in grayscale
    or black-and-white print. Even-indexed series use filled markers, odd-
    indexed series use hollow markers.

    Parameters
    ----------
    data : DataFrame, Series, dict, or array-like
        The series to plot. See module docstring for accepted shapes.
    x : str or array-like, optional
        Time variable. For a DataFrame, a string selects a column to use as
        the time axis; otherwise an array-like provides explicit x values.
        If None, the DataFrame/Series index (or a 0-based range) is used.
    y : str or sequence of str, optional
        For a DataFrame, restricts which columns to plot.
    labels : sequence of str, optional
        Override the legend labels (must match the number of series).
    colors : sequence of str, optional
        Override the per-series colors.
    title : str, optional
        Plot title. Defaults to None (no title).
    xtitle : str, optional
        Label for the x-axis. Defaults to None (detected from data).
    ytitle : str, optional
        Label for the y-axis. Defaults to ``"Value"``.
    linewidth : float
        Width of every line. Defaults to 3.
    markersize : float
        Size of the markers. Defaults to 7.
    marker_edge_width : float
        Width of the marker outlines. Defaults to 2.5.
    xtick_step : int, optional
        Explicit spacing between x ticks (numeric x only). If None, ticks
        are chosen automatically (at most ``max_ticks``).
    max_ticks : int
        Upper bound on the number of automatic x ticks. Defaults to 12.
    freq : str, optional
        Tick frequency for datetime x-axes. One of ``'day'``, ``'week'``,
        ``'month'``, ``'quarter'``, or ``'year'``. When set, the appropriate
        ``matplotlib.dates`` locator and formatter are applied and tick labels
        are auto-rotated 45°.
    ymin : float or None
        Lower limit of the y-axis. Defaults to None (automatic); pass a float to set a fixed minimum.
    show_legend : bool
        Whether to display the legend. Defaults to ``True``.
    legend_labels : sequence of str, optional
        Override the text of the legend entries. Must match the number of
        series.
    legend_loc : str
        Legend location (e.g. ``"upper left"``, ``"best"``). Defaults to
        ``"best"``.
    legend_bbox : tuple, optional
        ``bbox_to_anchor`` for the legend, e.g. ``(1.02, 1)``.
    title_loc : str
        Title horizontal alignment: ``"center"``, ``"left"``, or ``"right"``.
    title_pad : float
        Padding between the title and the axes. Defaults to 12.
    title_position : str
        ``"top"`` (default) or ``"bottom"``.
    note : str, optional
        Free-text note placed at the lower-left of the figure.
    grid : bool
        Whether to show a dashed grid on both axes. Defaults to False.
    show_values : bool
        Annotate each data point with its numeric value. Defaults to False.
        Labels are placed **above** local minima and **below** local maxima so
        they do not overlap with adjacent line segments.
    value_decimals : int
        Decimal places for ``show_values`` annotations. Defaults to 1.
    vlines : float or list of float, optional
        X-axis position(s) for vertical reference lines.
    vline_color : str
        Color of vertical lines. Defaults to ``"#d9534f"``.
    vline_linestyle : str
        Line style of vertical lines. Defaults to ``"--"``.
    vline_linewidth : float
        Width of vertical lines. Defaults to 1.5.
    shade : tuple or list of tuple, optional
        ``(xmin, xmax)`` interval(s) to shade, e.g. ``[(2008, 2009)]``.
    shade_color : str
        Fill color for shaded regions. Defaults to ``"#d0d0d0"``.
    shade_alpha : float
        Opacity of shaded regions (0–1). Defaults to 0.3.
    ax : matplotlib.axes.Axes, optional
        Existing axes to draw on. If None, a new figure and axes are created.
    unit : str, optional
        Unit label appended to the y-axis label, formatted as
        ``（单位：XX）``. Defaults to None.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    x_values, series, default_xlabel = _resolve_input(data, x, y)
    colors = _resolve_colors(colors, len(series))
    xtick_step = _validate_positive_step(
        "xtick_step",
        xtick_step,
        integer=True,
    )

    if labels is not None:
        labels = list(labels)
        if len(labels) != len(series):
            raise ValueError(
                f"labels has {len(labels)} entries but there are {len(series)} series."
            )
        series = {labels[i]: v for i, v in enumerate(series.values())}

    _ensure_fonts()
    ctx = _FigureContext(ax=ax)
    fig, ax = ctx.fig, ctx.ax

    draw_shade(ax, shade, shade_color, shade_alpha)
    draw_vlines(ax, vlines, vline_color, vline_linestyle, vline_linewidth)

    for i, (label, values) in enumerate(series.items()):
        color = (
            colors[i]
            if colors is not None
            else DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)]
        )
        linestyle = DEFAULT_LINESTYLES[i % len(DEFAULT_LINESTYLES)]
        marker = DEFAULT_MARKERS[i % len(DEFAULT_MARKERS)]
        is_even = i % 2 == 0
        ax.plot(
            x_values,
            values,
            linestyle=linestyle,
            linewidth=linewidth,
            marker=marker,
            markersize=markersize,
            color=color,
            markerfacecolor=color if is_even else "white",
            markeredgecolor=color,
            markeredgewidth=marker_edge_width,
            label=label,
        )

        if show_values:
            fmt = f".{value_decimals}f"
            n_pts = len(values)
            for idx, (xv, yv) in enumerate(zip(x_values, values, strict=False)):
                # Place label above a local low, below a local high so it does
                # not collide with the adjacent line segments.
                prev_y = float(values[idx - 1]) if idx > 0 else float(yv)
                next_y = float(values[idx + 1]) if idx < n_pts - 1 else float(yv)
                avg_nbr = (prev_y + next_y) / 2
                if float(yv) >= avg_nbr:  # local high → label below
                    y_off, va = -(markersize + 10), "top"
                else:  # local low  → label above
                    y_off, va = markersize + 4, "bottom"
                ax.annotate(
                    f"{yv:{fmt}}",
                    xy=(xv, yv),
                    xytext=(0, y_off),
                    textcoords="offset points",
                    ha="center",
                    va=va,
                    fontsize=11,
                    color=color,
                )

    ax.set_xlabel(
        xtitle if xtitle is not None else default_xlabel,
        fontsize=AXIS_LABEL_FONTSIZE,
    )
    if ytitle is not None:
        ax.set_ylabel(ytitle, fontsize=AXIS_LABEL_FONTSIZE)

    x_arr = np.asarray(x_values)
    is_datetime_x = np.issubdtype(x_arr.dtype, np.datetime64) or (
        pd.api.types.is_datetime64_any_dtype(x_arr)
    )
    is_numeric_x = np.issubdtype(x_arr.dtype, np.number)

    if is_datetime_x and freq is not None:
        _apply_freq_ticks(ax, x_values, freq, max_ticks=max_ticks)
    elif is_numeric_x:
        if xtick_step is not None:
            x_min, x_max = int(np.min(x_values)), int(np.max(x_values))
            ax.set_xticks(range(x_min, x_max + 1, xtick_step))
        else:
            ax.xaxis.set_major_locator(MaxNLocator(nbins=max_ticks))

    if ymin is not None:
        ax.set_ylim(bottom=ymin)

    labels = list(series.keys())
    ctx.finalize(
        title=title,
        title_position=title_position,
        title_loc=title_loc,
        title_pad=title_pad,
        note=note,
        grid=grid,
        show_legend=show_legend,
        legend_labels=legend_labels,
        legend_loc=legend_loc,
        legend_bbox=legend_bbox,
        labels=labels,
        unit=unit,
    )

    return fig, ax
