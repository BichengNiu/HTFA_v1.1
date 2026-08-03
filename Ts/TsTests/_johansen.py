"""Johansen cointegration test — trace and maximum eigenvalue tests.

Provides :class:`JohansenTest` and :class:`JohansenTestResult` for
determining the cointegration rank of a multivariate time series.
"""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np

from Ts.TsTests._base import BaseTest, BaseTestResult
from Ts.TsTests._utils import _clean_2d

# Map user-facing trend names to statsmodels det_order.
_TREND_TO_DET_ORDER = {
    "none": -1,
    "constant": 0,
    "trend": 1,
}

_CRIT_LABELS = {0: "10%", 1: "5%", 2: "1%"}


def _rejected_ranks(statistics, crit_vals, alpha_idx):
    """Return the set of rank indices where H0 is rejected.

    r is rejected if ``statistics[r] > crit_vals[r, alpha_idx]``.
    The sequential test guarantees rejected ranks are ``{0, 1, ..., rank-1}``.
    """
    k = len(statistics)
    return {r for r in range(k) if statistics[r] > crit_vals[r, alpha_idx]}


def _eig_fmt(val, row_idx):
    """Format eigenvalue for display.

    row 0 → ``"."``, otherwise 6 decimal places with leading zero stripped.
    """
    if row_idx == 0:
        return "."
    s = f"{val:.6f}".rstrip("0").rstrip(".")
    if val < 1 and val > 0:
        s = s.lstrip("0")
    return s


def _stat_fmt(val, row_idx, rejected_ranks):
    """Format a test statistic for display.

    Appends ``"*"`` for the first non-rejected row.
    """
    s = f"{val:.4f}"
    if row_idx not in rejected_ranks:
        s += "*"
    return s


def _build_table(
    rank_label, eigenvalues, statistics, crit_vals, rejected_ranks, alpha_idx=1
):
    """Build a single cointegration test table.

    Parameters
    ----------
    rank_label : str
        ``"Trace test"`` or ``"Max-eigenvalue test"``.
    eigenvalues : np.ndarray
    statistics : np.ndarray
    crit_vals : np.ndarray
        Critical values shape (k, 3) for [90%, 95%, 99%].
    rejected_ranks : set
        Set of rank indices where H0 was rejected.
    alpha_idx : int
        Column index for the displayed critical value (1 = 95%).

    Returns
    -------
    str
        Formatted table.
    """
    k = len(statistics)

    lines = [
        "-" * 79,
        f"{rank_label:>50s}",
        "-" * 79,
    ]
    cv_label = f"{_CRIT_LABELS[alpha_idx]} critical value"
    lines.append(
        f"{'rank':>5s}  {'eigenvalue':>11s}  {'statistic':>11s}  {cv_label:>18s}"
    )

    for r in range(k):
        eig_s = _eig_fmt(eigenvalues[r], r)
        stat_s = _stat_fmt(statistics[r], r, rejected_ranks)
        cv_s = f"{crit_vals[r, alpha_idx]:.4f}"
        lines.append(f"{r:>5d}  {eig_s:>11s}  {stat_s:>11s}  {cv_s:>18s}")
    lines.append("-" * 79)
    return "\n".join(lines)


@dataclass
class JohansenTestResult(BaseTestResult):
    """Result container for the Johansen cointegration test.

    Parameters
    ----------
    eigenvalues : np.ndarray
        Eigenvalues from the reduced rank regression, sorted descending (k,).
    trace_statistics : np.ndarray
        Trace test statistics for H0: rank <= r (k,).
    trace_critical_values : np.ndarray
        Trace test critical values, shape (k, 3) for [90%, 95%, 99%].
    maxeig_statistics : np.ndarray
        Maximum eigenvalue test statistics for H0: rank = r (k,).
    maxeig_critical_values : np.ndarray
        Max-eig test critical values, shape (k, 3) for [90%, 95%, 99%].
    rank : int
        Cointegration rank determined by sequential trace test at 5%.
    k : int
        Number of endogenous variables.
    trend_spec : str
        Deterministic trend specification used.
    cols : list of str
        Variable names.
    """

    eigenvalues: np.ndarray | None = None
    trace_statistics: np.ndarray | None = None
    trace_critical_values: np.ndarray | None = None
    maxeig_statistics: np.ndarray | None = None
    maxeig_critical_values: np.ndarray | None = None
    rank: int = 0
    k: int = 1
    trend_spec: str = ""
    cols: list | None = None

    def summary(self, alpha_idx=1):
        """Return formatted Johansen cointegration test results.

        Produces a Stata ``vecrank``-style output with header, trace test
        table, maximum eigenvalue test table, and cointegration rank
        conclusion.

        Parameters
        ----------
        alpha_idx : int
            Critical value column: 0 = 90%, 1 = 95%, 2 = 99%.

        Returns
        -------
        str
        """
        lines = [
            "Johansen tests for cointegration",
            f"Trend: {self.trend_spec}",
            f"Sample: 0 - {self.nobs - 1}",
            f"Lags = {self.lags}",
            "",
        ]

        trace_stat = self.trace_statistics
        trace_crit = self.trace_critical_values
        maxeig_stat = self.maxeig_statistics
        maxeig_crit = self.maxeig_critical_values

        trace_rejected = _rejected_ranks(trace_stat, trace_crit, alpha_idx)
        maxeig_rejected = _rejected_ranks(maxeig_stat, maxeig_crit, alpha_idx)

        lines.append(
            _build_table(
                "Trace test",
                self.eigenvalues,
                trace_stat,
                trace_crit,
                trace_rejected,
                alpha_idx,
            )
        )

        lines.append("")
        lines.append(
            _build_table(
                "Max-eigenvalue test",
                self.eigenvalues,
                maxeig_stat,
                maxeig_crit,
                maxeig_rejected,
                alpha_idx,
            )
        )

        trace_rank = len(trace_rejected)
        maxeig_rank = len(maxeig_rejected)
        lines.append("")
        lines.append(f"Cointegration rank (trace):       {trace_rank}")
        lines.append(f"Cointegration rank (max-eig):     {maxeig_rank}")

        return "\n".join(lines)

    def __str__(self):
        return self.summary()


def _sequential_rank(statistics, crit_vals, alpha_idx=1):
    """Determine cointegration rank by sequential testing.

    Starting from r = 0, test H0 using the statistic sequence.
    Reject H0 if ``statistics[r] > crit_vals[r, alpha_idx]``.
    The rank is the first r where we fail to reject H0.

    Parameters
    ----------
    statistics : np.ndarray
        Test statistics (trace or max-eig), shape (k,).
    crit_vals : np.ndarray
        Critical values (k, col) where col indexes significance levels.
    alpha_idx : int
        Column index for the desired significance level (0=90%, 1=95%, 2=99%).

    Returns
    -------
    int
        Estimated cointegration rank.
    """
    k = len(statistics)
    for r in range(k):
        if statistics[r] <= crit_vals[r, alpha_idx]:
            return r
    return k


class JohansenTest(BaseTest):
    """Johansen cointegration test for multivariate time series.

    Performs the Johansen (1988, 1991) trace and maximum eigenvalue tests
    to determine the cointegration rank.

    Parameters
    ----------
    data : array-like
        Time series data, shape (nobs, k). Must be 2-D with k >= 2.
    lags : int
        Number of lags in the VAR in levels (>= 2 for k_ar_diff >= 1).
    trend : str
        Deterministic trend specification:
        ``"none"`` (no deterministic terms), ``"constant"`` (constant,
        default), or ``"trend"`` (linear trend).
    cols : list of str, optional
        Variable names for display. Auto-generated if None.
    """

    _VALID_TRENDS = frozenset(_TREND_TO_DET_ORDER)

    def __init__(self, data, lags=2, trend="constant", cols=None):
        y = _clean_2d(data)
        if y.shape[1] < 2:
            raise ValueError(
                f"data must have at least 2 variables (k >= 2), got k = {y.shape[1]}"
            )
        if trend not in self._VALID_TRENDS:
            raise ValueError(
                f"trend must be one of {sorted(self._VALID_TRENDS)}, got {trend!r}"
            )
        if lags < 1:
            raise ValueError(f"lags must be >= 1, got {lags}")

        if cols is not None:
            if len(cols) != y.shape[1]:
                raise ValueError(
                    f"cols length ({len(cols)}) must match "
                    f"number of variables ({y.shape[1]})"
                )
            self.cols = list(cols)
        else:
            self.cols = [f"y{i}" for i in range(y.shape[1])]

        self.result_: JohansenTestResult | None = None
        self.data = y
        self.lags = lags
        self.trend = trend

    def fit(self):
        """Execute the Johansen cointegration test.

        Returns
        -------
        JohansenTestResult
        """
        from statsmodels.tsa.vector_ar.vecm import coint_johansen

        k_ar_diff = self.lags - 1
        det_order = _TREND_TO_DET_ORDER[self.trend]

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Casting complex values to real discards the imaginary part",
            )
            sm_result = coint_johansen(self.data, det_order, k_ar_diff)

        trace_stat = np.asarray(sm_result.trace_stat, dtype=float)
        maxeig_stat = np.asarray(sm_result.max_eig_stat, dtype=float)
        eig = np.real_if_close(np.asarray(sm_result.eig))
        if np.iscomplexobj(eig):
            max_imag = float(np.max(np.abs(np.imag(eig))))
            raise RuntimeError(
                f"Johansen eigenvalues have non-negligible imaginary parts: {max_imag}"
            )
        eig = np.asarray(eig, dtype=float)
        trace_crit = np.asarray(sm_result.trace_stat_crit_vals, dtype=float)
        maxeig_crit = np.asarray(sm_result.max_eig_stat_crit_vals, dtype=float)

        rank = _sequential_rank(trace_stat, trace_crit, alpha_idx=1)

        k = self.data.shape[1]
        result = JohansenTestResult(
            statistic=float(trace_stat[0]),
            pvalue=None,
            lags=self.lags,
            nobs=len(self.data),
            eigenvalues=eig,
            trace_statistics=trace_stat,
            trace_critical_values=trace_crit,
            maxeig_statistics=maxeig_stat,
            maxeig_critical_values=maxeig_crit,
            rank=rank,
            k=k,
            trend_spec=self.trend,
            cols=list(self.cols),
        )

        self.result_ = result
        return result
