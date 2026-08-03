"""SARIMA process simulation and SimSARIMAResult container.

Provides :func:`simulate_sarima` for generating synthetic time series from
SARIMA(p,d,q)(P,D,Q,s) models, and :class:`SimSARIMAResult` for storing and
visualising the generated data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.arima_process import ArmaProcess

from Ts.TsPlots import plot_series
from ._base import BaseSimResult
from ._validation import (
    normalize_coefficients,
    validate_order,
    validate_real,
    validate_sample,
)


@dataclass
class SimSARIMAResult(BaseSimResult):
    """Container for SARIMA simulation results.

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
        lines = [
            "SARIMA Simulation Result",
            "=" * 28,
            f"Order             : {p.get('order', 'N/A')}",
            f"Seasonal Order    : {p.get('seasonal_order', 'N/A')}",
            f"Observations      : {p.get('n', 'N/A')}",
            f"Burn-in           : {p.get('burn', 'N/A')}",
            f"Constant          : {p.get('const', 0.0):.4f}",
            f"sigma2            : {p.get('sigma2', 1.0):.4f}",
            f"Seed              : {p.get('seed', 'N/A')}",
        ]
        ar = p.get("ar")
        if ar:
            lines.append(f"AR coefficients   : {ar}")
        ma = p.get("ma")
        if ma:
            lines.append(f"MA coefficients   : {ma}")
        sar = p.get("seasonal_ar")
        if sar:
            lines.append(f"Seasonal AR coeff : {sar}")
        sma = p.get("seasonal_ma")
        if sma:
            lines.append(f"Seasonal MA coeff : {sma}")
        return "\n".join(lines)

    def plot(self, title=None, **kwargs):
        """Plot the generated time series.

        Uses :func:`TsPlots.plot_series` and :func:`TsPlots.style.style_axes`
        for unified styling.

        Parameters
        ----------
        title : str, optional
            Chart title. Defaults to a model-based title.
        **kwargs
            Forwarded to :func:`TsPlots.plot_series`.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        if title is None:
            title = f"SARIMA{self.params.get('order', '')} Simulation"

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
# Polynomial helpers
# ---------------------------------------------------------------------------


def _expand_seasonal_poly(coeffs, period):
    """Expand a seasonal polynomial into a high-order standard polynomial.

    Given seasonal coefficients [Phi_1, Phi_2, ...] and period s,
    returns the coefficients of Phi(B^s) = 1 - Phi_1 B^s - Phi_2 B^{2s} - ...

    Parameters
    ----------
    coeffs : list of float
        Seasonal AR or MA coefficients (without the leading 1).
    period : int
        Seasonal period (s).

    Returns
    -------
    np.ndarray
        Coefficients of the expanded polynomial including leading 1.
    """
    max_lag = len(coeffs) * period
    poly = np.zeros(max_lag + 1)
    poly[0] = 1.0
    for i, c in enumerate(coeffs):
        poly[(i + 1) * period] = -c
    return poly


def _build_ar_ma_polynomials(order, seasonal_order, ar, ma, seasonal_ar, seasonal_ma):
    """Build full AR and MA polynomials for a SARIMA model.

    The SARIMA(p,d,q)(P,D,Q,s) model is:
        phi(B) Phi(B^s) (1-B)^d (1-B^s)^D y_t = theta(B) Theta(B^s) epsilon_t

    The stationary AR polynomial is phi(B)*Phi(B^s) and the invertible MA
    polynomial is theta(B)*Theta(B^s).  Differencing operators are applied later
    via cumulative summation.

    Returns
    -------
    ar_poly : np.ndarray
        Full AR polynomial coefficients (including leading 1).
    ma_poly : np.ndarray
        Full MA polynomial coefficients (including leading 1).
    d : int
        Regular differencing order.
    D : int
        Seasonal differencing order.
    s : int
        Seasonal period.
    """
    _p, _d, _q = order
    _P, _D, _Q, s = seasonal_order

    # Non-seasonal AR polynomial: 1 - phi_1 B - phi_2 B^2 - ...
    ar_poly = np.array([1.0])
    if ar:
        ar_vec = np.array([1.0] + [-c for c in ar])
        ar_poly = ar_vec

    # Seasonal AR polynomial
    if seasonal_ar:
        seasonal_ar_poly = _expand_seasonal_poly(seasonal_ar, s)
        ar_poly = np.convolve(ar_poly, seasonal_ar_poly)

    # Non-seasonal MA polynomial: 1 + theta_1 B + theta_2 B^2 + ...
    ma_poly = np.array([1.0])
    if ma:
        ma_vec = np.array([1.0, *list(ma)])
        ma_poly = ma_vec

    # Seasonal MA polynomial
    if seasonal_ma:
        seasonal_ma_poly = _expand_seasonal_poly(seasonal_ma, s)
        ma_poly = np.convolve(ma_poly, seasonal_ma_poly)

    return ar_poly, ma_poly


def _apply_inverse_differencing(data, d, D, s):
    """Apply inverse differencing to recover the integrated series.

    (1-B)^d (1-B^s)^D y_t = data_t  recover y_t

    Parameters
    ----------
    data : np.ndarray
        Stationary ARMA series.
    d : int
        Regular differencing order.
    D : int
        Seasonal differencing order.
    s : int
        Seasonal period.

    Returns
    -------
    np.ndarray
        Integrated series (same length).
    """
    y = data.copy()
    # Regular integration: cumsum d times
    for _ in range(d):
        y = np.cumsum(y)
    # Seasonal integration: (1 - B^s)^{-1} = y_t = x_t + y_{t-s}
    for _ in range(D):
        for i in range(s, len(y)):
            y[i] = y[i] + y[i - s]
    return y


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def simulate_sarima(
    n: int = 200,
    order: tuple[int, int, int] = (1, 0, 0),
    seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0),
    ar: list[float] | None = None,
    ma: list[float] | None = None,
    seasonal_ar: list[float] | None = None,
    seasonal_ma: list[float] | None = None,
    const: float = 0.0,
    sigma2: float = 1.0,
    seed: int | None = None,
    burn: int = 100,
) -> SimSARIMAResult:
    """Simulate a SARIMA(p,d,q)(P,D,Q,s) time series.

    Parameters
    ----------
    n : int
        Number of observations to generate (after burn-in).
    order : tuple
        ``(p, d, q)`` non-seasonal order.
    seasonal_order : tuple
        ``(P, D, Q, s)`` seasonal order.
    ar : float or list of float, optional
        Non-seasonal AR coefficients [phi_1, phi_2, ...].  A single float is
        automatically wrapped.  If omitted and p > 0, defaults to
        ``[0.5] * p``.
    ma : float or list of float, optional
        Non-seasonal MA coefficients [theta_1, theta_2, ...].  A single float is
        automatically wrapped.  If omitted and q > 0, defaults to
        ``[0.3] * q``.
    seasonal_ar : float or list of float, optional
        Seasonal AR coefficients [Phi_1, Phi_2, ...].  A single float is
        automatically wrapped.  Defaults to ``[0.3] * P``.
    seasonal_ma : float or list of float, optional
        Seasonal MA coefficients [Theta_1, Theta_2, ...].  A single float is
        automatically wrapped.  Defaults to ``[0.2] * Q``.
    const : float
        Constant (drift) term.
    sigma2 : float
        Innovation variance.
    seed : int, optional
        Random seed for reproducibility.
    burn : int
        Number of burn-in observations to discard.

    Returns
    -------
    SimSARIMAResult
        Container with ``.data``, ``.residuals``, ``.params``, and methods
        ``.get_data()``, ``.get_params()``, ``.summary()``, ``.plot()``.
    """
    n, burn = validate_sample(n, burn)
    order = validate_order("order", order, length=3)
    seasonal_order = validate_order("seasonal_order", seasonal_order, length=4)
    p, d, q = order
    P, D, Q, s = seasonal_order
    if (P > 0 or D > 0 or Q > 0) and s < 2:
        raise ValueError(
            "seasonal_order period s must be >= 2 when seasonal terms are used"
        )
    const = validate_real("const", const)
    sigma2 = validate_real("sigma2", sigma2, positive=True)

    ar = normalize_coefficients("ar", ar, length=p, default=0.5)
    ma = normalize_coefficients("ma", ma, length=q, default=0.3)
    seasonal_ar = normalize_coefficients(
        "seasonal_ar", seasonal_ar, length=P, default=0.3
    )
    seasonal_ma = normalize_coefficients(
        "seasonal_ma", seasonal_ma, length=Q, default=0.2
    )

    # Build full AR / MA polynomials
    ar_poly, ma_poly = _build_ar_ma_polynomials(
        order,
        seasonal_order,
        ar,
        ma,
        seasonal_ar,
        seasonal_ma,
    )

    rng = np.random.default_rng(seed)
    total_n = n + burn

    # Pre-generate all white-noise innovations from a single RNG
    innovations = rng.standard_normal(total_n)

    # Use the same innovations for ARMA generation and result residuals
    arma_process = ArmaProcess(ar_poly, ma_poly)
    arma_data = arma_process.generate_sample(
        nsample=(total_n,),
        scale=np.sqrt(sigma2),
        distrvs=lambda size: innovations,
    )

    errors = innovations * np.sqrt(sigma2)

    # Add constant to the stationary component
    arma_data = arma_data + const

    # Apply inverse differencing
    integrated = _apply_inverse_differencing(arma_data, d, D, s)

    # Discard burn-in
    result_data = integrated[burn:]
    result_residuals = errors[burn:]

    params = {
        "order": order,
        "seasonal_order": seasonal_order,
        "ar": ar,
        "ma": ma,
        "seasonal_ar": seasonal_ar,
        "seasonal_ma": seasonal_ma,
        "const": const,
        "sigma2": sigma2,
        "seed": seed,
        "n": n,
        "burn": burn,
    }

    return SimSARIMAResult(data=result_data, residuals=result_residuals, params=params)
