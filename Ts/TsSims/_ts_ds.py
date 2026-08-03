"""Trend-stationary (TS) and difference-stationary (DS) process simulation.

Provides :func:`simulate_trend_stationary` and
:func:`simulate_difference_stationary` for generating the two canonical
non-stationary time series used in Chapter 5 teaching examples, plus the
:class:`SimTSDSResult` container.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from Ts.TsPlots import plot_series
from ._base import BaseSimResult
from ._validation import validate_real, validate_sample


@dataclass
class SimTSDSResult(BaseSimResult):
    """Container for TS / DS simulation results.

    Provides the standard three-method interface (``get_data``,
    ``get_params``, ``plot``) consistent with :class:`SimSARIMAResult` and
    :class:`SimGARCHResult`.

    Parameters
    ----------
    data : np.ndarray
        Generated time series of length *n*.
    residuals : np.ndarray
        White-noise innovations used in generation.
    params : dict
        All parameters used for simulation.
    """

    def summary(self) -> str:
        """Return a formatted parameter summary string.

        Returns
        -------
        str
        """
        p = self.params
        process_type = p.get("process_type", "N/A")
        label = {
            "trend_stationary": "TS (Trend-Stationary)",
            "difference_stationary": "DS (Difference-Stationary)",
        }.get(process_type, process_type)

        lines = [
            f"{label} Simulation Result",
            "=" * 40,
            f"Observations      : {p.get('n', 'N/A')}",
        ]
        if "intercept" in p:
            lines.append(f"Intercept         : {p['intercept']:.4f}")
        if "slope" in p:
            lines.append(f"Slope             : {p['slope']:.4f}")
        if "drift" in p:
            lines.append(f"Drift             : {p['drift']:.4f}")
        lines.append(f"sigma             : {p.get('sigma', 'N/A')}")
        lines.append(f"Seed              : {p.get('seed', 'N/A')}")
        if "burn" in p:
            lines.append(f"Burn-in           : {p.get('burn', 'N/A')}")
        return "\n".join(lines)

    def plot(self, title=None, **kwargs):
        """Plot the generated time series.

        Uses :func:`TsPlots.plot_series` for unified styling.

        Parameters
        ----------
        title : str, optional
            Chart title. Defaults to a process-type based title.
        **kwargs
            Forwarded to :func:`TsPlots.plot_series`.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        if title is None:
            process_type = self.params.get("process_type", "TS/DS")
            label = {
                "trend_stationary": "Trend-Stationary (TS)",
                "difference_stationary": "Difference-Stationary (DS)",
            }.get(process_type, process_type)
            title = f"{label} Process Simulation"

        fig, ax = plot_series(
            self.data,
            title=title,
            ytitle="Value",
            xtitle="Time",
            show_legend=False,
            **kwargs,
        )
        return fig, ax


# ---------------------------------------------------------------------------
# Public simulation functions
# ---------------------------------------------------------------------------


def simulate_trend_stationary(
    n: int = 100,
    intercept: float = 0.0,
    slope: float = 1.0,
    sigma: float = 1.0,
    seed: int | None = None,
) -> SimTSDSResult:
    """Simulate a trend-stationary (TS) process.

    The TS model ::

        y_t = intercept + slope * t + epsilon_t
        epsilon_t ~ N(0, sigma^2)

    A TS process is stationary *around* a deterministic linear trend.
    Shocks have only transitory effects -- the series always reverts to
    the trend line.

    Parameters
    ----------
    n : int
        Number of observations to generate.
    intercept : float
        Intercept term (level at t=0).
    slope : float
        Slope (deterministic trend coefficient).
    sigma : float
        Standard deviation of the Gaussian innovations.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    SimTSDSResult
        Container with ``.data``, ``.residuals``, ``.params`` and methods
        ``.get_data()``, ``.get_params()``, ``.summary()``, ``.plot()``.
    """
    n, _ = validate_sample(n)
    intercept = validate_real("intercept", intercept)
    slope = validate_real("slope", slope)
    sigma = validate_real("sigma", sigma, positive=True)

    rng = np.random.default_rng(seed)
    errors = rng.normal(0.0, sigma, size=n)
    t = np.arange(n, dtype=float)
    data = intercept + slope * t + errors
    return SimTSDSResult(
        data=data,
        residuals=errors,
        params={
            "process_type": "trend_stationary",
            "intercept": intercept,
            "slope": slope,
            "sigma": sigma,
            "seed": seed,
            "n": n,
        },
    )


def simulate_difference_stationary(
    n: int = 100,
    drift: float = 0.0,
    sigma: float = 1.0,
    seed: int | None = None,
    burn: int = 50,
) -> SimTSDSResult:
    """Simulate a difference-stationary (DS) process (random walk with drift).

    The DS model ::

        y_t = drift + y_{t-1} + epsilon_t,   y_0 = 0
        epsilon_t ~ N(0, sigma^2)

    A DS process is non-stationary but becomes stationary after first
    differencing. Shocks have permanent effects -- the series never
    reverts to any fixed path.

    Parameters
    ----------
    n : int
        Number of observations to generate (after burn-in).
    drift : float
        Drift term (average period-to-period change).
    sigma : float
        Standard deviation of the Gaussian innovations.
    seed : int, optional
        Random seed for reproducibility.
    burn : int
        Number of burn-in observations to discard. Default 50.

    Returns
    -------
    SimTSDSResult
        Container with ``.data``, ``.residuals``, ``.params`` and methods
        ``.get_data()``, ``.get_params()``, ``.summary()``, ``.plot()``.
    """
    n, burn = validate_sample(n, burn)
    drift = validate_real("drift", drift)
    sigma = validate_real("sigma", sigma, positive=True)

    total_n = n + burn
    rng = np.random.default_rng(seed)
    errors = rng.normal(0.0, sigma, size=total_n)
    y = np.zeros(total_n)
    for t in range(1, total_n):
        y[t] = drift + y[t - 1] + errors[t]
    return SimTSDSResult(
        data=y[burn:],
        residuals=errors[burn:],
        params={
            "process_type": "difference_stationary",
            "drift": drift,
            "sigma": sigma,
            "seed": seed,
            "n": n,
            "burn": burn,
        },
    )
