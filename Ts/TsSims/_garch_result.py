"""Result container for GARCH-family simulation output.

Provides :class:`SimGARCHResult` — the unified container for all
GARCH-family simulation results (GARCH, GJR-GARCH, EGARCH, IGARCH, GARCH-M).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from Ts.TsPlots import plot_series
from Ts.TsPlots.style import (
    DEFAULT_PALETTE,
    FIGSIZE,
    style_axes,
)
from ._base import BaseSimResult


@dataclass
class SimGARCHResult(BaseSimResult):
    """Container for GARCH-family simulation results.

    Handles all GARCH variants: pure ARCH (q = 0), GARCH (q >= 1),
    GJR-GARCH, EGARCH, IGARCH, and GARCH-M.

    Parameters
    ----------
    data : np.ndarray
        Generated time series of length *n*.
    residuals : np.ndarray
        Mean-corrected innovations (epsilon_t = sigma_t * u_t).
    conditional_volatility : np.ndarray
        Conditional standard deviations sigma_t.
    params : dict
        All parameters used for simulation.
    """

    conditional_volatility: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def conditional_variance(self) -> np.ndarray:
        """Conditional variance sigma2_t = sigma_t^2.

        Returns
        -------
        np.ndarray
            Squared conditional volatility, length *n*.
        """
        return self.conditional_volatility**2

    @property
    def model_type(self) -> str:
        """Model type stored in the canonical parameter mapping."""
        value = self.params.get("model_type")
        if not isinstance(value, str) or not value:
            raise ValueError("params must contain a non-empty 'model_type'")
        return value

    def summary(self) -> str:
        """Return a formatted parameter summary string.

        Returns
        -------
        str
        """
        p = self.params
        model_type = self.model_type

        lines = [
            f"{model_type} Simulation Result",
            "=" * 28,
        ]
        o_val = p.get("o", 0)
        if o_val > 0:
            lines.append(
                f"Order             : p={p.get('p', 0)}, o={o_val}, q={p.get('q', 0)}"
            )
        else:
            lines.append(f"Order             : p={p.get('p', 0)}, q={p.get('q', 0)}")
        lines.append(f"omega             : {p.get('omega', 0.0):.4f}")
        lines.append(f"alpha             : {p.get('alpha', [])}")

        gamma = p.get("gamma")
        if gamma:
            lines.append(f"gamma             : {gamma}")
        beta = p.get("beta")
        if beta:
            lines.append(f"beta              : {beta}")

        garch_m_kappa = p.get("garch_m_kappa")
        if garch_m_kappa is not None:
            lines.append(f"ARCH-in-mean kappa: {garch_m_kappa:.4f}")
            lines.append(f"ARCH-in-mean form : {p.get('garch_m_form', 'N/A')}")

        lines += [
            f"Mean model        : {p.get('mean_model', 'N/A')}",
            f"Mean constant     : {p.get('mean_const', 0.0):.4f}",
            f"Distribution      : {p.get('dist', 'N/A')}",
            f"Observations      : {p.get('n', 'N/A')}",
            f"Burn-in           : {p.get('burn', 'N/A')}",
            f"Seed              : {p.get('seed', 'N/A')}",
        ]
        return "\n".join(lines)

    def plot(self, title=None, **kwargs):
        """Plot the generated series and conditional volatility.

        Two-panel figure: top = data, bottom = conditional volatility sigma_t.
        Uses :class:`TsPlots.style` constants for unified styling.

        Parameters
        ----------
        title : str, optional
            Suptitle for the figure.
        **kwargs
            Forwarded to :func:`TsPlots.plot_series`.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : numpy.ndarray of matplotlib.axes.Axes
        """
        import matplotlib.pyplot as plt

        model_type = self.model_type
        if title is None:
            title = (
                f"{model_type}({self.params.get('p', 0)},"
                f"{self.params.get('q', 0)}) Simulation"
            )

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(FIGSIZE[0], FIGSIZE[1] * 1.6))

        # Panel 1: Data
        plot_series(
            self.data,
            ax=ax1,
            title=f"{model_type} Simulated Series",
            ytitle="Value",
            show_legend=False,
            **kwargs,
        )

        # Panel 2: Conditional volatility
        ax2.plot(
            self.conditional_volatility,
            color=DEFAULT_PALETTE[1],
            linewidth=2,
            label="Conditional Volatility ($\\sigma_t$)",
        )
        ax2.set_xlabel("Time")
        ax2.set_ylabel("Volatility ($\\sigma_t$)")
        ax2.set_title("Conditional Volatility")
        ax2.legend(frameon=False, fontsize=10)
        style_axes(ax2)

        fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.tight_layout()
        return fig, np.array([ax1, ax2])

    def to_dataframe(self) -> pd.DataFrame:
        """Return data, residuals, and volatility as a DataFrame.

        Returns
        -------
        pd.DataFrame
            Columns: ``data``, ``residuals``, ``volatility``.
        """
        return pd.DataFrame(
            {
                "data": self.data,
                "residuals": self.residuals,
                "volatility": self.conditional_volatility,
            }
        )
