"""TsSims — Time series simulation toolkit.

This package provides functions for generating synthetic time series from
SARIMA, GARCH models, cointegrated systems, and TS/DS processes, with
structured result objects.

Main interfaces
---------------
simulate_sarima
    Generate SARIMA(p,d,q)(P,D,Q,s) data.
simulate_garch
    Generate GARCH(p,q) data with time-varying volatility.  Handles both
    pure ARCH (q = 0) and GARCH (q >= 1) processes.
simulate_igarch
    Generate IGARCH(p,q) data with sum(alpha)+sum(beta)=1 constraint.
simulate_gjr_garch
    Generate GJR-GARCH(p,o,q) data with leverage effects.
simulate_egarch
    Generate EGARCH(p,o,q) data with log-variance dynamics.
simulate_garch_m
    Generate GARCH-M(p,q) data with volatility-in-mean.
simulate_cointegrated
    Generate cointegrated multivariate data via VECM representation.
simulate_trend_stationary
    Generate a trend-stationary (TS) process.
simulate_difference_stationary
    Generate a difference-stationary (DS) process (random walk with drift).

Result classes
--------------
SimSARIMAResult
    Container for SARIMA simulation output. Provides ``.get_data()``,
    ``.get_params()``, ``.summary()``, ``.plot()``.
SimGARCHResult
    Container for GARCH simulation output. Provides ``.get_data()``,
    ``.get_params()``, ``.summary()``, ``.plot()``, ``.to_dataframe()``.
SimCointegratedResult
    Container for cointegrated simulation output. Provides ``.get_data()``,
    ``.get_params()``, ``.summary()``, ``.plot()``.
SimTSDSResult
    Container for TS/DS simulation output. Provides ``.get_data()``,
    ``.get_params()``, ``.summary()``, ``.plot()``.

Quick start
-----------
>>> from Ts.TsSims import simulate_sarima, simulate_garch
>>> from Ts.TsSims import simulate_cointegrated
>>> from Ts.TsSims import simulate_trend_stationary, simulate_difference_stationary

>>> # AR(1) with default coefficients
>>> r = simulate_sarima(n=100, order=(1, 0, 0), seed=42)
>>> r.plot()

>>> # ARCH(1) (GARCH with q=0)
>>> r = simulate_garch(n=200, p=1, q=0, omega=0.4, alpha=[0.5], seed=42)
>>> print(r.summary())

>>> # GARCH(1,1)
>>> r = simulate_garch(n=200, p=1, q=1, omega=0.2, alpha=[0.3], beta=[0.5], seed=42)
>>> df = r.to_dataframe()

>>> # Cointegrated system (k=2, r=1)
>>> import numpy as np
>>> alpha = np.array([[-0.3], [0.0]])
>>> beta  = np.array([[1.0], [-1.0]])
>>> r = simulate_cointegrated(n=500, k=2, coint_rank=1,
...                            alpha=alpha, beta=beta, seed=42)
>>> df = r.get_data()
>>> r.plot()

>>> # Trend-stationary process
>>> r = simulate_trend_stationary(n=200, intercept=1.0, slope=0.5, seed=42)
>>> r.plot()
"""

from ._base import BaseSimResult
from ._cointegration import SimCointegratedResult, simulate_cointegrated
from ._garch_result import SimGARCHResult
from ._sarima import SimSARIMAResult, simulate_sarima
from ._garch import simulate_garch, simulate_igarch
from ._garch_ext import (
    simulate_garch_m,
    simulate_gjr_garch,
    simulate_egarch,
)
from ._ts_ds import (
    SimTSDSResult,
    simulate_trend_stationary,
    simulate_difference_stationary,
)

__all__ = [
    # Base
    "BaseSimResult",
    "SimCointegratedResult",
    "SimGARCHResult",
    # Result classes
    "SimSARIMAResult",
    "SimTSDSResult",
    "simulate_cointegrated",
    "simulate_difference_stationary",
    "simulate_egarch",
    "simulate_garch",
    "simulate_garch_m",
    "simulate_gjr_garch",
    "simulate_igarch",
    # Functions
    "simulate_sarima",
    "simulate_trend_stationary",
]
