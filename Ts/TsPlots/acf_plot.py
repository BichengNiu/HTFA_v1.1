"""Autocorrelation and partial-autocorrelation plots for the plots package.

The two main entry points are :func:`plot_acf` and :func:`plot_pacf`. Both
follow the same style conventions as :mod:`TsPlots.ts_plot` and
:mod:`TsPlots.sc_plot`: colorblind-friendly palette, Times New Roman / FangSong
typography, hidden top/right spines, and optional dashed grid.

Accepted input
--------------
- 1-D numpy array
- pandas Series
- single-column pandas DataFrame

Confidence bands
----------------
The shaded region represents a symmetric confidence band at the requested
level (default 95 %). For ACF, Bartlett's formula is used by default so the
band width varies by lag. For PACF the band is uniform (±z / √n). Pass
``alpha=0.01`` for a 99 % band, ``alpha=0.10`` for a 90 % band, etc.

Examples
--------
>>> from Ts.TsPlots import plot_acf, plot_pacf
>>> fig, ax = plot_acf(residuals, nlags=20)
>>> fig, ax = plot_pacf(residuals, nlags=20, alpha=0.01)
>>> # embed in an existing subplot grid
>>> fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
>>> plot_acf(series, ax=ax1)
>>> plot_pacf(series, ax=ax2)
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import acf as sm_acf
from statsmodels.tsa.stattools import pacf as sm_pacf

from .style import (
    AXIS_LABEL_FONTSIZE,
    DEFAULT_PALETTE,
    FIGSIZE,
    TITLE_FONTSIZE,
    draw_note_and_bottom_title,
    style_axes,
)


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------


def _to_1d(data) -> np.ndarray:
    """Convert supported input types to a 1-D numpy array.

    Parameters
    ----------
    data : array-like, pandas Series, or single-column pandas DataFrame
        Input data.

    Returns
    -------
    numpy.ndarray
        1-D float array.

    Raises
    ------
    ValueError
        If a DataFrame with more than one column is passed, or if the array
        is not 1-D.
    """
    if isinstance(data, pd.DataFrame):
        if data.shape[1] != 1:
            raise ValueError(
                f"DataFrame must have exactly one column; got {data.shape[1]}."
            )
        return data.iloc[:, 0].to_numpy(dtype=float)
    if isinstance(data, pd.Series):
        return data.to_numpy(dtype=float)
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"Data must be 1-D; got shape {arr.shape}.")
    return arr


# ---------------------------------------------------------------------------
# Shared rendering core
# ---------------------------------------------------------------------------


def _draw_correlogram(
    ax,
    lags: np.ndarray,
    values: np.ndarray,
    conf_band: np.ndarray,
    *,
    bar_color: str,
    band_color: str,
    band_alpha: float,
    xtitle: str,
    ytitle: str,
    title: str | None,
    title_position: str,
    max_ticks: int,
    grid: bool,
    note: str | None,
    fig,
):
    """Render bars, zero line, and confidence band onto *ax*.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Target axes.
    lags : 1-D array of int
        Lag indices (x positions).
    values : 1-D array of float
        Correlation coefficients (y values).
    conf_band : 1-D array of float
        Half-width of the confidence band at each lag. Always positive. May
        be uniform (all equal) or lag-varying (Bartlett).
    bar_color : str
        Fill colour for the bars.
    band_color : str
        Fill colour of the confidence region.
    band_alpha : float
        Opacity of the confidence region (0–1).
    xtitle : str
        X-axis label.
    ytitle : str
        Y-axis label.
    title : str or None
        Optional top title.
    title_position : str
        ``"top"`` or ``"bottom"``.
    max_ticks : int
        Upper bound on the number of x-axis tick marks. When the number of
        lags exceeds this value, ``MaxNLocator`` is used so tick labels
        remain readable.
    grid : bool
        Whether to draw a dashed grid.
    note : str or None
        Figure-level note placed at the lower left.
    fig : matplotlib.figure.Figure
        Parent figure (needed for tight_layout and note/bottom-title
        placement).
    """
    # --- Confidence band ---------------------------------------------------
    # Extend half a unit beyond the first and last lag so the band covers the
    # full width of the outermost bars (bar width = 0.3, axis margin ≈ 0.5).
    x_fill = np.concatenate([[lags[0] - 0.5], lags, [lags[-1] + 0.5]])
    band_fill = np.concatenate([[conf_band[0]], conf_band, [conf_band[-1]]])
    ax.fill_between(
        x_fill,
        -band_fill,
        +band_fill,
        color=band_color,
        alpha=band_alpha,
        linewidth=0,
        zorder=0,
    )

    # --- Zero reference line -----------------------------------------------
    ax.axhline(0, color="black", linewidth=0.8, zorder=1)

    # --- Correlation bars --------------------------------------------------
    ax.bar(
        lags,
        values,
        width=0.3,
        color=bar_color,
        zorder=2,
    )

    # --- Axis labels -------------------------------------------------------
    ax.set_xlabel(xtitle, fontsize=AXIS_LABEL_FONTSIZE)
    ax.set_ylabel(ytitle, fontsize=AXIS_LABEL_FONTSIZE)

    # --- X-axis ticks ------------------------------------------------------
    # Show every lag when there are few enough; otherwise let MaxNLocator
    # choose an integer-valued subset (mirrors ts_plot's max_ticks logic).
    if len(lags) <= max_ticks:
        ax.set_xticks(lags)
    else:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=max_ticks, integer=True))

    # --- Optional title ----------------------------------------------------
    if title is not None and title_position == "top":
        ax.set_title(title, fontsize=TITLE_FONTSIZE, fontweight="bold", pad=12)

    style_axes(ax, grid=grid)

    fig.tight_layout()
    draw_note_and_bottom_title(
        fig,
        note=note,
        title=title,
        title_position=title_position,
    )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def plot_acf(
    data,
    nlags: int = 40,
    *,
    alpha: float = 0.05,
    bartlett_confint: bool = True,
    zero_lag: bool = True,
    title: str | None = None,
    xtitle: str = "滞后期数",
    ytitle: str = "ACF值",
    bar_color: str | None = None,
    band_color: str = "#d0d0d0",
    band_alpha: float = 0.4,
    max_ticks: int = 12,
    grid: bool = False,
    note: str | None = None,
    title_position: str = "top",
    ax=None,
):
    """Plot the sample autocorrelation function with a confidence band.

    Parameters
    ----------
    data : array-like or pandas Series or single-column DataFrame
        The time series whose ACF is plotted.
    nlags : int
        Number of lags to compute and display. Defaults to 40.
    alpha : float
        Significance level for the confidence band. ``0.05`` gives a 95 % band
        (default), ``0.01`` gives 99 %, ``0.10`` gives 90 %, etc.
    bartlett_confint : bool
        Use Bartlett's lag-varying formula for the confidence interval width
        (``True``, default) rather than the uniform ±z / √n formula
        (``False``).
    zero_lag : bool
        Include lag 0 (ACF = 1 by definition) in the plot. Defaults to
        ``True``.
    title : str, optional
        Plot title. Defaults to None (no title).
    xtitle : str
        X-axis label. Defaults to ``"滞后期数"`` (Lag Number).
    ytitle : str
        Y-axis label. Defaults to ``"ACF值"`` (ACF Value).
    bar_color : str, optional
        Bar colour. Defaults to ``DEFAULT_PALETTE[0]`` (deep blue).
    band_color : str
        Confidence-band fill colour. Defaults to ``"#d0d0d0"`` (light gray).
    band_alpha : float
        Confidence-band opacity (0–1). Defaults to 0.4.
    max_ticks : int
        Upper bound on the number of x-axis tick marks. When the number of
        displayed lags exceeds this value, ``MaxNLocator`` selects an integer
        subset. Defaults to 12.
    grid : bool
        Whether to draw a dashed grid. Defaults to False.
    note : str, optional
        Free-text note placed at the lower left of the figure.
    title_position : str
        ``"top"`` (default) or ``"bottom"``.
    ax : matplotlib.axes.Axes, optional
        Existing axes to draw on. If None, a new figure and axes are created.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    x = _to_1d(data)
    color = bar_color if bar_color is not None else DEFAULT_PALETTE[0]

    acf_vals, confint = sm_acf(
        x,
        nlags=nlags,
        alpha=alpha,
        fft=True,
        bartlett_confint=bartlett_confint,
    )

    # confint shape: (nlags+1, 2) — absolute lower/upper bounds.
    # Half-width = upper_bound − centre (symmetric, always positive).
    conf_band = confint[:, 1] - acf_vals

    lags = np.arange(len(acf_vals))  # 0, 1, …, nlags

    if not zero_lag:
        lags = lags[1:]
        acf_vals = acf_vals[1:]
        conf_band = conf_band[1:]

    if ax is None:
        fig, ax = plt.subplots(figsize=FIGSIZE)
    else:
        fig = ax.figure

    _draw_correlogram(
        ax,
        lags,
        acf_vals,
        conf_band,
        bar_color=color,
        band_color=band_color,
        band_alpha=band_alpha,
        xtitle=xtitle,
        ytitle=ytitle,
        title=title,
        title_position=title_position,
        max_ticks=max_ticks,
        grid=grid,
        note=note,
        fig=fig,
    )

    return fig, ax


def plot_pacf(
    data,
    nlags: int = 40,
    *,
    alpha: float = 0.05,
    method: str = "ywm",
    title: str | None = None,
    xtitle: str = "滞后期数",
    ytitle: str = "PACF值",
    bar_color: str | None = None,
    band_color: str = "#d0d0d0",
    band_alpha: float = 0.4,
    max_ticks: int = 12,
    grid: bool = False,
    note: str | None = None,
    title_position: str = "top",
    ax=None,
):
    """Plot the sample partial autocorrelation function with a confidence band.

    Parameters
    ----------
    data : array-like or pandas Series or single-column DataFrame
        The time series whose PACF is plotted.
    nlags : int
        Number of lags to compute and display. Defaults to 40. Must be less
        than ``len(data) // 2``.
    alpha : float
        Significance level for the confidence band. ``0.05`` gives a 95 % band
        (default), ``0.01`` gives 99 %, ``0.10`` gives 90 %, etc.
    method : str
        PACF estimation method passed to ``statsmodels``. Common choices:
        ``"ywm"`` (Yule-Walker with bias correction, default), ``"ols"``,
        ``"ld"``.
    title : str, optional
        Plot title. Defaults to None (no title).
    xtitle : str
        X-axis label. Defaults to ``"滞后期数"`` (Lag Number).
    ytitle : str
        Y-axis label. Defaults to ``"PACF值"`` (PACF Value).
    bar_color : str, optional
        Bar colour. Defaults to ``DEFAULT_PALETTE[0]`` (deep blue).
    band_color : str
        Confidence-band fill colour. Defaults to ``"#d0d0d0"`` (light gray).
    band_alpha : float
        Confidence-band opacity (0–1). Defaults to 0.4.
    max_ticks : int
        Upper bound on the number of x-axis tick marks. When the number of
        displayed lags exceeds this value, ``MaxNLocator`` selects an integer
        subset. Defaults to 12.
    grid : bool
        Whether to draw a dashed grid. Defaults to False.
    note : str, optional
        Free-text note placed at the lower left of the figure.
    title_position : str
        ``"top"`` (default) or ``"bottom"``.
    ax : matplotlib.axes.Axes, optional
        Existing axes to draw on. If None, a new figure and axes are created.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    x = _to_1d(data)
    color = bar_color if bar_color is not None else DEFAULT_PALETTE[0]

    pacf_vals, confint = sm_pacf(
        x,
        nlags=nlags,
        alpha=alpha,
        method=method,
    )

    # confint shape: (nlags+1, 2) — absolute lower/upper bounds.
    # Half-width = upper_bound − centre (symmetric, always positive).
    conf_band = confint[:, 1] - pacf_vals

    # PACF at lag 0 is always 1 by construction; skip it for a cleaner plot.
    lags = np.arange(1, len(pacf_vals))
    pacf_vals = pacf_vals[1:]
    conf_band = conf_band[1:]

    if ax is None:
        fig, ax = plt.subplots(figsize=FIGSIZE)
    else:
        fig = ax.figure

    _draw_correlogram(
        ax,
        lags,
        pacf_vals,
        conf_band,
        bar_color=color,
        band_color=band_color,
        band_alpha=band_alpha,
        xtitle=xtitle,
        ytitle=ytitle,
        title=title,
        title_position=title_position,
        max_ticks=max_ticks,
        grid=grid,
        note=note,
        fig=fig,
    )

    return fig, ax
