"""Reusable plotting utilities for scatter plots.

The main entry point is :func:`plot_scatter`, which draws an arbitrary number
of point series. Styling cycles per series: even-indexed series use filled
markers, odd-indexed series use hollow markers, with colors from a
colorblind-friendly palette. Typography, palette, and axes styling are shared
with :mod:`TsPlots.ts_plot` through :mod:`TsPlots.style`.

Unlike a time series, each scatter series has its own ``x`` *and* ``y`` values,
and both axes accept an independent unit label (``x_unit`` / ``y_unit``).

Accepted inputs
---------------
- pandas DataFrame : ``x`` and ``y`` name columns; an optional ``group`` column
  splits the data into one series per distinct value.
- dict             : ``{label: (x_values, y_values)}`` for multiple named series.
- 2D array         : columns 0 and 1 are taken as x and y of a single series.
- arrays           : ``x`` and ``y`` passed directly as array-likes.

Examples
--------
>>> import numpy as np, pandas as pd
>>> from Ts.TsPlots import plot_scatter
>>> # DataFrame, two columns
>>> df = pd.DataFrame({"a": [1, 2, 3], "b": [3, 2, 1]})
>>> fig, ax = plot_scatter(df, x="a", y="b")
>>> # DataFrame split by a grouping column
>>> df2 = pd.DataFrame({"a": [1,2,3,4], "b": [3,2,1,0], "g": ["x","x","y","y"]})
>>> fig, ax = plot_scatter(df2, x="a", y="b", group="g")
>>> # dict of (x, y) pairs
>>> fig, ax = plot_scatter({"s1": ([1, 2, 3], [3, 2, 1])})
>>> # bare arrays with a trend line and unit labels
>>> fig, ax = plot_scatter(x=[1,2,3], y=[2,4,5], fit_line=True, x_unit="元", y_unit="人")
"""

from __future__ import annotations

from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from .style import (
    _ensure_fonts,
    _FigureContext,
    _resolve_colors,
    _validate_positive_step,
    DEFAULT_PALETTE,
    DEFAULT_MARKERS,
    AXIS_LABEL_FONTSIZE,
    TITLE_FONTSIZE,
    draw_shade,
    draw_vlines,
    draw_hlines,
)


def _resolve_scatter_input(data, x, y, group):
    """Normalize supported inputs into (series_list, default_xlabel,
    default_ylabel).

    series_list is a list of (label, x_array, y_array) tuples preserving order.
    """
    if isinstance(data, pd.DataFrame):
        if not isinstance(x, str) or not isinstance(y, str):
            raise ValueError("For a DataFrame, pass x and y as column-name strings.")
        if x not in data.columns:
            raise KeyError(f"Column {x!r} not found in DataFrame.")
        if y not in data.columns:
            raise KeyError(f"Column {y!r} not found in DataFrame.")

        if group is not None:
            if group not in data.columns:
                raise KeyError(f"Column {group!r} not found in DataFrame.")
            series = []
            for key, sub in data.groupby(group, sort=False):
                series.append((str(key), sub[x].to_numpy(), sub[y].to_numpy()))
            return series, x, y

        return [(str(y), data[x].to_numpy(), data[y].to_numpy())], x, y

    if isinstance(data, dict):
        series = []
        for label, pair in data.items():
            xv, yv = pair
            series.append((str(label), np.asarray(xv), np.asarray(yv)))
        return series, "x", "y"

    if data is None:
        if x is None or y is None:
            raise ValueError("Provide either `data`, or both `x` and `y`.")
        return [("Series 1", np.asarray(x), np.asarray(y))], "x", "y"

    arr = np.asarray(data)
    if arr.ndim == 2 and arr.shape[1] >= 2:
        return [("Series 1", arr[:, 0], arr[:, 1])], "x", "y"

    raise TypeError(
        f"Unsupported data type/shape: {type(data)!r}. Pass a DataFrame with "
        "x/y column names, a dict of (x, y) pairs, a 2D array, or x and y "
        "arrays directly."
    )


def plot_scatter(
    data=None,
    x=None,
    y=None,
    *,
    group=None,
    labels=None,
    colors=None,
    title=None,
    xtitle=None,
    ytitle=None,
    markersize=7,
    marker_edge_width=2.5,
    xtick_step=None,
    ytick_step=None,
    max_ticks=12,
    ymin=None,
    show_legend=True,
    legend_labels=None,
    legend_loc="best",
    legend_bbox=None,
    title_loc="center",
    title_pad=12,
    title_position="top",
    note=None,
    grid=False,
    vlines=None,
    vline_color="#d9534f",
    vline_linestyle="--",
    vline_linewidth=1.5,
    hlines=None,
    hline_color="#d9534f",
    hline_linestyle="--",
    hline_linewidth=1.5,
    shade=None,
    shade_color="#d0d0d0",
    shade_alpha=0.3,
    alpha=0.7,
    fit_line=False,
    fit_linewidth=2,
    fit_linestyle="--",
    show_values=False,
    value_decimals=1,
    equal_aspect=False,
    ax=None,
    x_unit=None,
    y_unit=None,
):
    """Plot an arbitrary number of scatter series with cycling styles.

    Styling cycles per series so each series differs in color and marker shape,
    keeping series distinguishable even in grayscale or black-and-white print.
    Even-indexed series use filled markers, odd-indexed series use hollow
    markers. Typography, palette, and axes styling match
    :func:`TsPlots.ts_plot.plot_series`.

    Parameters
    ----------
    data : DataFrame, dict, or array-like, optional
        The series to plot. See module docstring for accepted shapes. May be
        omitted when passing ``x`` and ``y`` arrays directly.
    x : str or array-like, optional
        For a DataFrame, the column name for the x-axis. Otherwise an
        array-like of x values for a single series.
    y : str or array-like, optional
        For a DataFrame, the column name for the y-axis. Otherwise an
        array-like of y values for a single series.
    group : str, optional
        For a DataFrame, a column whose distinct values split the data into one
        series each. Defaults to None (a single series).
    labels : sequence of str, optional
        Override the series labels (must match the number of series).
    colors : sequence of str, optional
        Override the per-series colors.
    title : str, optional
        Plot title. Defaults to None (no title).
    xtitle : str, optional
        Label for the x-axis. Defaults to None (detected from data).
    ytitle : str, optional
        Label for the y-axis. Defaults to None (detected from data).
    markersize : float
        Size of the markers. Defaults to 7.
    marker_edge_width : float
        Width of the marker outlines. Defaults to 2.5.
    xtick_step : float or None
        Explicit spacing between x-axis ticks. Defaults to None (automatic).
    ytick_step : float or None
        Explicit spacing between y-axis ticks. Defaults to None (automatic).
    max_ticks : int
        Upper bound on the number of automatic ticks for both axes. Defaults
        to 12.
    ymin : float or None
        Lower limit of the y-axis. Defaults to None (automatic).
    show_legend : bool
        Whether to display the legend. Defaults to True.
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
    vlines : float or list of float, optional
        X-axis position(s) for vertical reference lines.
    vline_color : str
        Color of vertical lines. Defaults to ``"#d9534f"``.
    vline_linestyle : str
        Line style of vertical lines. Defaults to ``"--"``.
    vline_linewidth : float
        Width of vertical lines. Defaults to 1.5.
    hlines : float or list of float, optional
        Y-axis position(s) for horizontal reference lines.
    hline_color : str
        Color of horizontal lines. Defaults to ``"#d9534f"``.
    hline_linestyle : str
        Line style of horizontal lines. Defaults to ``"--"``.
    hline_linewidth : float
        Width of horizontal lines. Defaults to 1.5.
    shade : tuple or list of tuple, optional
        ``(xmin, xmax)`` interval(s) to shade.
    shade_color : str
        Fill color for shaded regions. Defaults to ``"#d0d0d0"``.
    shade_alpha : float
        Opacity of shaded regions (0–1). Defaults to 0.3.
    alpha : float
        Opacity of the scatter points (0–1). Defaults to 0.7.
    fit_line : bool
        Whether to draw a least-squares (degree-1) trend line per series.
        Defaults to False.
    fit_linewidth : float
        Width of the trend line. Defaults to 2.
    fit_linestyle : str
        Line style of the trend line. Defaults to ``"--"``.
    show_values : bool
        Annotate each point with a ``(x, y)`` label. Defaults to False.
        Each label is offset in the direction **away from its nearest
        neighbour** to reduce mutual overlap.
    value_decimals : int
        Decimal places for ``show_values`` annotations. Defaults to 1.
    equal_aspect : bool
        Set an equal aspect ratio. Defaults to False.
    ax : matplotlib.axes.Axes, optional
        Existing axes to draw on. If None, a new figure and axes are created.
    x_unit : str, optional
        Unit label appended to the x-axis label, formatted as ``（单位：XX）``.
    y_unit : str, optional
        Unit label appended to the y-axis label, formatted as ``（单位：XX）``.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    series, default_xlabel, default_ylabel = _resolve_scatter_input(data, x, y, group)
    colors = _resolve_colors(colors, len(series))
    xtick_step = _validate_positive_step("xtick_step", xtick_step)
    ytick_step = _validate_positive_step("ytick_step", ytick_step)

    if labels is not None:
        labels = list(labels)
        if len(labels) != len(series):
            raise ValueError(
                f"labels has {len(labels)} entries but there are {len(series)} series."
            )
        series = [(labels[i], xv, yv) for i, (_, xv, yv) in enumerate(series)]

    _ensure_fonts()
    ctx = _FigureContext(ax=ax)
    fig, ax = ctx.fig, ctx.ax

    draw_shade(ax, shade, shade_color, shade_alpha)
    draw_vlines(ax, vlines, vline_color, vline_linestyle, vline_linewidth)
    draw_hlines(ax, hlines, hline_color, hline_linestyle, hline_linewidth)

    for i, (label, x_vals, y_vals) in enumerate(series):
        color = (
            colors[i]
            if colors is not None
            else DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)]
        )
        marker = DEFAULT_MARKERS[i % len(DEFAULT_MARKERS)]
        is_even = i % 2 == 0
        ax.scatter(
            x_vals,
            y_vals,
            s=markersize**2,
            marker=marker,
            facecolors=color if is_even else "white",
            edgecolors=color,
            linewidths=marker_edge_width,
            alpha=alpha,
            label=label,
            zorder=3,
        )

        if fit_line:
            x_num = np.asarray(x_vals, dtype=float)
            y_num = np.asarray(y_vals, dtype=float)
            mask = ~(np.isnan(x_num) | np.isnan(y_num))
            if mask.sum() >= 2:
                coeffs = np.polyfit(x_num[mask], y_num[mask], 1)
                x_fit = np.linspace(x_num[mask].min(), x_num[mask].max(), 200)
                ax.plot(
                    x_fit,
                    np.polyval(coeffs, x_fit),
                    color=color,
                    linestyle=fit_linestyle,
                    linewidth=fit_linewidth,
                    zorder=2,
                )

        if show_values:
            fmt = f".{value_decimals}f"
            xarr = np.asarray(x_vals, dtype=float)
            yarr = np.asarray(y_vals, dtype=float)
            n_pts = len(xarr)
            # Normalise coordinates so x and y axes contribute equally to
            # distance calculations regardless of scale differences.
            x_span = xarr.max() - xarr.min() if xarr.max() != xarr.min() else 1.0
            y_span = yarr.max() - yarr.min() if yarr.max() != yarr.min() else 1.0
            xn = xarr / x_span
            yn = yarr / y_span

            for j in range(n_pts):
                if n_pts > 1:
                    # Direction away from the nearest neighbouring point.
                    dx_all = xn - xn[j]
                    dy_all = yn - yn[j]
                    dists = np.sqrt(dx_all**2 + dy_all**2)
                    dists[j] = np.inf
                    nn = int(np.argmin(dists))
                    dx = xn[j] - xn[nn]
                    dy = yn[j] - yn[nn]
                    mag = np.sqrt(dx**2 + dy**2)
                    if mag > 0:
                        dx, dy = dx / mag, dy / mag
                    else:
                        dx, dy = 0.0, 1.0
                else:
                    dx, dy = 0.0, 1.0

                off_x = dx * (markersize + 6)
                off_y = dy * (markersize + 6)
                va = "bottom" if off_y >= 0 else "top"
                ha = (
                    "center"
                    if abs(off_x) < markersize / 2
                    else ("left" if off_x > 0 else "right")
                )
                ax.annotate(
                    f"({xarr[j]:{fmt}}, {yarr[j]:{fmt}})",
                    xy=(xarr[j], yarr[j]),
                    xytext=(off_x, off_y),
                    textcoords="offset points",
                    ha=ha,
                    va=va,
                    fontsize=11,
                    color=color,
                )

    if title is not None and title_position == "top":
        ax.set_title(
            title,
            fontsize=TITLE_FONTSIZE,
            fontweight="bold",
            loc=title_loc,
            pad=title_pad,
        )
    ax.set_xlabel(
        xtitle if xtitle is not None else default_xlabel,
        fontsize=AXIS_LABEL_FONTSIZE,
    )
    ax.set_ylabel(
        ytitle if ytitle is not None else default_ylabel,
        fontsize=AXIS_LABEL_FONTSIZE,
    )

    if xtick_step is not None:
        x_all = np.concatenate([xv for _, xv, _ in series], dtype=float)
        x_min = float(np.nanmin(x_all))
        x_max = float(np.nanmax(x_all))
        ax.set_xticks(
            np.arange(
                np.floor(x_min / xtick_step) * xtick_step,
                x_max + xtick_step,
                xtick_step,
            )
        )
    else:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=max_ticks))

    if ytick_step is not None:
        y_all = np.concatenate([yv for _, _, yv in series], dtype=float)
        y_data_min = float(np.nanmin(y_all))
        y_data_max = float(np.nanmax(y_all))
        ax.set_yticks(
            np.arange(
                np.floor(y_data_min / ytick_step) * ytick_step,
                y_data_max + ytick_step,
                ytick_step,
            )
        )
    else:
        ax.yaxis.set_major_locator(MaxNLocator(nbins=max_ticks))

    if ymin is not None:
        ax.set_ylim(bottom=ymin)

    if equal_aspect:
        ax.set_aspect("equal")

    labels = [lbl for lbl, _, _ in series]
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
        x_unit=x_unit,
        y_unit=y_unit,
    )

    return fig, ax
