"""TsPlots — Shared plotting toolkit.

This package unifies time-series plotting (:mod:`TsPlots.ts_plot`), scatter
plotting (:mod:`TsPlots.sc_plot`), and autocorrelation plotting
(:mod:`TsPlots.acf_plot`) under a common interface, sharing fonts, colour
palette, and axis styling via :mod:`TsPlots.style`.

Main interfaces
---------------
plot_series
    Time-series line chart; accepts DataFrame / Series / dict / array-like.
plot_scatter
    Scatter chart; accepts DataFrame / dict / arrays; supports grouping and
    trend lines.
plot_acf
    Sample autocorrelation function bar chart with confidence band.
plot_pacf
    Sample partial autocorrelation function bar chart with confidence band.

Quick start
-----------
>>> from Ts.TsPlots import plot_series, plot_scatter, plot_acf, plot_pacf
>>> fig, ax = plot_series(df, title="GDP Growth Rate")
>>> fig, ax = plot_scatter(df, x="Income", y="Consumption", fit_line=True)

Advanced usage — style constants and helpers
--------------------------------------------
>>> from Ts.TsPlots.style import DEFAULT_PALETTE, style_axes, apply_fonts
"""

from .ts_plot import plot_series
from .sc_plot import plot_scatter
from .acf_plot import plot_acf, plot_pacf

__all__ = [
    "plot_acf",
    "plot_pacf",
    "plot_scatter",
    "plot_series",
]
