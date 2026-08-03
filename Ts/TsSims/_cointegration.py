"""Cointegrated multivariate time series simulation.

Provides :func:`simulate_cointegrated` and :class:`SimCointegratedResult`
for generating k-dimensional time series with a known cointegration structure.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ._base import BaseSimResult
from ._validation import validate_int, validate_real, validate_sample


@dataclass
class SimCointegratedResult(BaseSimResult):
    """Container for cointegrated simulation results.

    Provides the standard interface (``get_data``, ``get_params``, ``summary``,
    ``plot``) consistent with :class:`SimSARIMAResult`, :class:`SimGARCHResult`,
    and :class:`SimTSDSResult`.

    Parameters
    ----------
    data : np.ndarray
        Generated multivariate time series of shape ``(n, k)``.
    residuals : np.ndarray
        Structural innovations of shape ``(n, k)``.
    params : dict
        All parameters used for simulation.
    """

    # get_data() is inherited from BaseSimResult — handles 2D data correctly.

    def summary(self) -> str:
        """Return a formatted parameter summary string.

        Returns
        -------
        str
        """
        p = self.params
        k = p["k"]
        r = p["coint_rank"]
        n = p["n"]

        lines = [
            "Cointegrated System Simulation Result",
            "=" * 50,
            f"Variables (k)     : {k}",
            f"Coint. rank (r)   : {r}",
            f"Observations      : {n}",
            f"sigma             : {p['sigma']}",
            f"Seed              : {p['seed']}",
            f"Burn-in           : {p['burn']}",
            "",
            "alpha (adjustment):",
        ]
        alpha = p.get("alpha")
        if alpha is not None:
            lines.append(f"{alpha}")
        lines.append("")
        lines.append("beta (coint. vectors):")
        beta = p.get("beta")
        if beta is not None:
            lines.append(f"{beta}")
        return "\n".join(lines)

    def plot(self, title=None, **kwargs):
        """Plot the generated multivariate time series.

        Each variable is drawn in its own subplot using
        :func:`TsPlots.plot_series` for unified styling.

        Parameters
        ----------
        title : str, optional
            Suptitle for the figure.
        **kwargs
            Forwarded to :func:`TsPlots.plot_series`.

        Returns
        -------
        fig : matplotlib.figure.Figure
        axes : numpy.ndarray of matplotlib.axes.Axes
        """
        from Ts.TsPlots import plot_series
        import matplotlib.pyplot as plt

        k = self.data.shape[1]
        fig, axes = plt.subplots(k, 1, figsize=(10, 2.5 * k), sharex=True)

        if title is None:
            title = "Cointegrated System Simulation"

        for i in range(k):
            plot_series(
                self.data[:, i],
                title="",
                ytitle=f"y{i}",
                xtitle="",
                show_legend=False,
                ax=axes[i],
                **kwargs,
            )

        axes[-1].set_xlabel("Time")
        fig.suptitle(title, fontweight="bold")
        fig.tight_layout()
        return fig, axes


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _make_default_beta(k: int, r: int) -> np.ndarray:
    """Build default cointegrating vectors: [I_r; 0_{(k-r) x r}]."""
    beta = np.zeros((k, r))
    beta[:r, :r] = np.eye(r)
    return beta


def _make_default_alpha(k: int, r: int) -> np.ndarray:
    """Build default adjustment matrix: -0.5 * I_r on top, zeros below."""
    alpha = np.zeros((k, r))
    alpha[:r, :r] = -0.5 * np.eye(r)
    return alpha


def _check_stability(alpha: np.ndarray, beta: np.ndarray) -> None:
    """Verify that the VECM is stable: |eig(I_r + beta' @ alpha)| < 1."""
    M = np.eye(beta.shape[1]) + beta.T @ alpha
    eigenvalues = np.linalg.eigvals(M)
    if np.any(np.abs(eigenvalues) >= 1.0):
        raise ValueError(
            f"Unstable VECM: max|eig(I_r + beta'@alpha)| = "
            f"{np.max(np.abs(eigenvalues)):.4f} >= 1.0. "
            f"Choose alpha/beta such that all eigenvalues lie inside the unit circle."
        )


def _validate_params(
    k: int,
    coint_rank: int,
    alpha: np.ndarray | None,
    beta: np.ndarray | None,
) -> None:
    """Validate all simulation parameters."""
    if k < 2:
        raise ValueError(f"k must be >= 2, got {k}")
    if coint_rank < 1:
        raise ValueError(f"coint_rank must be >= 1, got {coint_rank}")
    if coint_rank >= k:
        raise ValueError(f"coint_rank ({coint_rank}) must be < k ({k})")

    if alpha is not None and (alpha.ndim != 2 or alpha.shape != (k, coint_rank)):
        raise ValueError(
            f"alpha must have shape ({k}, {coint_rank}), got {alpha.shape}"
        )

    if beta is not None and (beta.ndim != 2 or beta.shape != (k, coint_rank)):
        raise ValueError(f"beta must have shape ({k}, {coint_rank}), got {beta.shape}")


# ---------------------------------------------------------------------------
# Public simulation function
# ---------------------------------------------------------------------------


def simulate_cointegrated(
    n: int = 200,
    k: int = 2,
    coint_rank: int = 1,
    alpha: np.ndarray | None = None,
    beta: np.ndarray | None = None,
    sigma: float = 1.0,
    seed: int | None = None,
    burn: int = 100,
) -> SimCointegratedResult:
    """Simulate a cointegrated multivariate time series.

    Data is generated from the VECM representation ::

        Delta Y_t = alpha @ beta.T @ Y_{t-1} + epsilon_t
        epsilon_t ~ N(0, sigma^2 * I_k)

    where *alpha* (k x r) controls the speed of adjustment and *beta* (k x r)
    contains the cointegrating vectors.  The matrix :math:`beta^T Y_t` yields
    *r* stationary linear combinations (cointegrating relations).

    Parameters
    ----------
    n : int
        Number of observations to generate (after burn-in).
    k : int
        Number of variables (k >= 2).
    coint_rank : int
        Cointegration rank r (1 <= r < k).
    alpha : np.ndarray of shape (k, r), optional
        Adjustment coefficient matrix.  Default: ``-0.5 * I_r`` stacked on
        zeros for the remaining ``k - r`` rows.
    beta : np.ndarray of shape (k, r), optional
        Cointegrating vector matrix.  Default: ``[I_r; 0]``.
    sigma : float
        Standard deviation of the Gaussian innovations.
    seed : int, optional
        Random seed for reproducibility.
    burn : int
        Number of burn-in observations to discard.  Default 100.

    Returns
    -------
    SimCointegratedResult
        Container with ``.data`` (n x k), ``.residuals`` (n x k), ``.params``
        and methods ``.get_data()``, ``.get_params()``, ``.summary()``,
        ``.plot()``.

    Examples
    --------
    >>> from Ts.TsSims import simulate_cointegrated
    >>>
    >>> # Two cointegrated variables (k=2, r=1) with default parameters
    >>> r = simulate_cointegrated(n=200, k=2, coint_rank=1, seed=42)
    >>> df = r.get_data()
    >>> print(r.summary())
    >>>
    >>> # Custom alpha and beta
    >>> import numpy as np
    >>> alpha = np.array([[-0.3], [0.0]])
    >>> beta  = np.array([[1.0], [-1.0]])
    >>> r = simulate_cointegrated(n=500, k=2, coint_rank=1,
    ...                           alpha=alpha, beta=beta, seed=42)
    """
    # --- validate -----------------------------------------------------------
    n, burn = validate_sample(n, burn)
    k = validate_int("k", k, minimum=2)
    coint_rank = validate_int("coint_rank", coint_rank, minimum=1)
    sigma = validate_real("sigma", sigma, positive=True)
    if coint_rank >= k:
        raise ValueError(f"coint_rank ({coint_rank}) must be < k ({k})")

    if alpha is None:
        alpha = _make_default_alpha(k, coint_rank)
    else:
        alpha = np.asarray(alpha, dtype=float)
    if beta is None:
        beta = _make_default_beta(k, coint_rank)
    else:
        beta = np.asarray(beta, dtype=float)

    _validate_params(k, coint_rank, alpha, beta)
    if not np.all(np.isfinite(alpha)):
        raise ValueError("alpha must contain only finite values")
    if not np.all(np.isfinite(beta)):
        raise ValueError("beta must contain only finite values")
    _check_stability(alpha, beta)

    # --- generate -----------------------------------------------------------
    total_n = n + burn
    rng = np.random.default_rng(seed)
    innovations = rng.normal(0.0, sigma, size=(total_n, k))

    Y = np.zeros((total_n, k))
    for t in range(1, total_n):
        y_prev = Y[t - 1]
        ect = beta.T @ y_prev  # (r,) — cointegration errors
        Y[t] = y_prev + alpha @ ect + innovations[t]

    data = Y[burn:]  # (n, k)
    errors = innovations[burn:]  # (n, k)

    return SimCointegratedResult(
        data=data,
        residuals=errors,
        params={
            "k": k,
            "coint_rank": coint_rank,
            "alpha": alpha.copy(),
            "beta": beta.copy(),
            "sigma": sigma,
            "seed": seed,
            "n": n,
            "burn": burn,
        },
    )
