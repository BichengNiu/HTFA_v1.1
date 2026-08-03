"""Shared plotting helper for unit root test results.

Used by ADF, Phillips-Perron, KPSS, Perron, and Zivot-Andrews result
classes to render diagnostic charts.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from Ts.TsPlots.style import (
    DEFAULT_PALETTE,
    FIGSIZE,
    LEGEND_FONTSIZE,
    style_axes,
)


def _render_critical_value_plot(result, test_name, ax=None):
    """Render the test statistic against 1% / 5% / 10% critical values.

    Parameters
    ----------
    result : BaseTestResult
        Result object with ``.critical_values`` (dict) and ``.statistic``.
    test_name : str
        Display label (e.g. ``"ADF"``, ``"Phillips-Perron"``, ``"KPSS"``).
    ax : matplotlib.axes.Axes, optional
        Axes to draw on. If ``None``, a new figure is created.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=FIGSIZE)
    else:
        fig = ax.figure

    crit = result.critical_values
    if not crit:
        ax.text(
            0.5,
            0.5,
            "No critical values available",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        style_axes(ax)
        fig.tight_layout()
        return fig, ax

    # Sort sig levels numerically descending: 10%, 5%, 1%
    def _parse_pct(k):
        return float(k.replace("%", ""))

    sig_levels = sorted(crit.keys(), key=_parse_pct, reverse=True)
    crit_vals = [crit[k] for k in sig_levels]
    labels = sig_levels  # Use keys directly as labels

    # Horizontal lines for critical values with colour coding
    colors = [DEFAULT_PALETTE[2], DEFAULT_PALETTE[0], DEFAULT_PALETTE[3]]
    for i, (lab, cv) in enumerate(zip(labels, crit_vals, strict=False)):
        color = colors[i % len(colors)]
        ax.axhline(
            cv,
            color=color,
            linestyle="--",
            linewidth=1.5 if i == 1 else 1.0,
            alpha=0.8,
            label=f"{lab} critical value: {cv:.3f}",
        )

    # Test statistic as a scatter point
    ax.scatter(
        0,
        result.statistic,
        color=DEFAULT_PALETTE[4],
        s=120,
        zorder=5,
        label=f"Test statistic: {result.statistic:.3f}",
    )

    ax.set_xticks([])
    ax.set_ylabel("Statistic")
    ax.set_title(f"{test_name}: Test Statistic vs Critical Values")

    # Determine legend location based on test direction
    # KPSS: reject (non-stationary) when statistic > critical value (right tail)
    # ADF/PP: reject (stationary) when statistic < critical value (left tail)
    ax.legend(frameon=False, fontsize=LEGEND_FONTSIZE)

    style_axes(ax)
    fig.tight_layout()
    return fig, ax


# ---------------------------------------------------------------------------
# Zivot-Andrews (1992) plot helpers
# ---------------------------------------------------------------------------


def _render_tstat_plot(result, ax=None):
    """Render the t-statistic sequence across candidate break points."""
    if ax is None:
        fig, ax = plt.subplots(figsize=FIGSIZE)
    else:
        fig = ax.figure

    years = result.all_break_years
    t_stats_arr = result.all_t_stats

    ax.plot(
        years,
        t_stats_arr,
        color=DEFAULT_PALETTE[0],
        linewidth=2,
        marker="o",
        markersize=4,
        markerfacecolor="white",
        markeredgecolor=DEFAULT_PALETTE[0],
        markeredgewidth=1.5,
        label="t(rho-hat)",
    )

    # Highlight the minimum
    min_idx = np.argmin(t_stats_arr)
    ax.axvline(
        years[min_idx],
        color=DEFAULT_PALETTE[4],
        linestyle="--",
        linewidth=1.5,
        alpha=0.7,
        label=f"Optimal break: {years[min_idx]:.0f}",
    )

    # Critical value lines
    ax.axhline(
        result.cv_05,
        color=DEFAULT_PALETTE[2],
        linestyle=":",
        linewidth=1.5,
        alpha=0.8,
        label=f"5% critical value ({result.cv_05:.2f})",
    )
    ax.axhline(
        result.cv_01,
        color=DEFAULT_PALETTE[3],
        linestyle=":",
        linewidth=1.5,
        alpha=0.8,
        label=f"1% critical value ({result.cv_01:.2f})",
    )

    ax.set_xlabel("Break year")
    ax.set_ylabel("t(rho-hat) = rho-hat / s.e.")
    ax.set_title(
        f"Zivot-Andrews (1992) - Model {result.model}\n"
        f"Sequential t-statistics for all candidate break points"
    )
    ax.legend(frameon=False, fontsize=LEGEND_FONTSIZE)
    style_axes(ax)

    fig.tight_layout()
    return fig, ax


def _render_ic_plot(result, ax=None):
    """Render the information criterion across lag orders."""
    if ax is None:
        fig, ax = plt.subplots(figsize=FIGSIZE)
    else:
        fig = ax.figure

    ic_values = result.ic_by_lag
    ks = np.arange(len(ic_values))
    mask = ~np.isnan(ic_values)
    valid_ks = ks[mask]
    valid_ic = ic_values[mask]
    best_k = result.lags

    ic_label = result.lag_method.upper()

    ax.plot(
        valid_ks,
        valid_ic,
        color=DEFAULT_PALETTE[0],
        linewidth=2,
        marker="o",
        markersize=6,
        markerfacecolor="white",
        markeredgecolor=DEFAULT_PALETTE[0],
        markeredgewidth=1.5,
    )

    # Highlight minimum
    ax.axvline(
        best_k,
        color=DEFAULT_PALETTE[4],
        linestyle="--",
        linewidth=1.5,
        alpha=0.7,
        label=f"Optimal k = {best_k}",
    )

    ax.set_xlabel("Number of lags (k)")
    ax.set_ylabel(ic_label)
    ax.set_title(
        f"Zivot-Andrews (1992) - Model {result.model}\n"
        f"{ic_label} for each lag order at optimal break point "
        f"({result.break_year:.0f})"
    )
    ax.legend(frameon=False, fontsize=LEGEND_FONTSIZE)
    style_axes(ax)

    # Ensure integer ticks on x-axis
    ax.set_xticks(valid_ks)

    fig.tight_layout()
    return fig, ax
