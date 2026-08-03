"""Toda-Yamamoto (1995) Granger causality test.

Implements the Toda-Yamamoto procedure for testing Granger causality
in possibly integrated or cointegrated VAR systems.  By augmenting the
VAR with *d_max* extra lags and testing only the first *p* lags, the
Wald statistic retains its asymptotic chi-squared distribution
regardless of whether the series are I(0), I(1), or cointegrated.

Reference
---------
Toda, H. Y., & Yamamoto, T. (1995).  Statistical inference in vector
autoregressions with possibly integrated processes.  *Journal of
Econometrics*, 66(1-2), 225-250.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats as scipy_stats

from Ts.TsTests._base import BaseMultiTestResult, BaseTest
from Ts.TsTests._utils import _clean_2d

# Significance used by automatic integration-order detection.
_AUTO_DMAX_ALPHA = 0.10

# Valid trend specifications for the VAR in levels.
_VALID_TRENDS = frozenset({"c", "ct", "n"})


def _sig_star(p_value):
    """Return significance star code.

    ``**`` p<0.01, ``*`` p<0.05, ``.`` p<0.10, `` `` otherwise.
    """
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    if p_value < 0.10:
        return "."
    return " "


@dataclass
class _TYEntry:
    """Single Toda-Yamamoto test entry (internal).

    Parameters
    ----------
    test_statistic : float
        Wald chi-squared statistic.
    p_value : float
        p-value from chi-squared distribution.
    df : int
        Degrees of freedom (p for pairwise, p*(k-1) for ALL).
    caused : str
        Name of the caused variable.
    causing : list of str
        Name(s) of the causing variable(s).
    """

    test_statistic: float
    p_value: float
    df: int
    caused: str
    causing: list


@dataclass
class TodaYamamotoTestResult(BaseMultiTestResult):
    """Result container for the Toda-Yamamoto Granger causality test.

    Parameters
    ----------
    tests : list of _TYEntry
        Individual test entries for each (caused, causing) pair.
    p : int
        Lag order used for causality testing.
    d_max : int
        Maximum order of integration used.
    k : int
        Number of endogenous variables.
    cols : list of str
        Variable names.
    """

    tests: list = field(default_factory=list)
    p: int = 1
    d_max: int = 0
    k: int = 1
    cols: list = field(default_factory=list)

    def summary(self) -> str:
        """Return a formatted Stata-style Toda-Yamamoto test table.

        Returns
        -------
        str
        """
        if not self.tests:
            return "No Toda-Yamamoto test results."

        entries = self.tests

        max_caused = max(len(e.caused) for e in entries)
        max_causing = max(len(", ".join(e.causing)) for e in entries)
        eq_w = max(max_caused, 8) + 2
        ex_w = max(max_causing, 8) + 2

        total_w = eq_w + ex_w + 40
        top_rule = "=" * total_w
        sep_rule = "-" * total_w

        lines = [
            "Toda-Yamamoto Granger Causality Wald Tests",
            f"  VAR lags (p): {self.p}  |  d_max: {self.d_max}",
            top_rule,
            f"{'Equation':<{eq_w}s} {'Excluded':<{ex_w}s} {'chi2':>10s} {'df':>8s} {'p-value':>10s}",
            sep_rule,
        ]

        prev_caused = None
        for e in entries:
            if prev_caused is not None and e.caused != prev_caused:
                lines.append(sep_rule)
            prev_caused = e.caused

            cause_str = ", ".join(e.causing)
            sig = _sig_star(e.p_value)

            lines.append(
                f"{e.caused:<{eq_w}s} {cause_str:<{ex_w}s} "
                f"{e.test_statistic:>10.4f} {e.df:>8d} {e.p_value:>10.4f} {sig}"
            )

        lines.append(top_rule)
        lines.append("Significance codes:  ** p<0.01  * p<0.05  . p<0.10")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary()

    def __len__(self) -> int:
        return len(self.tests)

    def __iter__(self):
        return iter(self.tests)

    def __getitem__(self, index):
        return self.tests[index]


class TodaYamamotoTest(BaseTest):
    """Toda-Yamamoto (1995) Granger causality test.

    Tests Granger causality in possibly integrated or cointegrated VAR
    systems without requiring pre-tests for unit roots or cointegration.

    The procedure:
    1. Determine *d_max*, the maximum order of integration.
    2. Estimate a VAR(*p* + *d_max*) in levels.
    3. Test zero restrictions on the first *p* lags only.

    Parameters
    ----------
    data : array-like
        Time series data, shape (nobs, k).  Must be 2-D with k >= 2.
    p : int
        Lag order for causality testing (p >= 1).
    d_max : int or None
        Maximum order of integration.  If None (default), automatically
        detected via ADF test on each variable.  Valid values: 0, 1, 2.
    trend : str
        Deterministic trend for the VAR: ``"c"`` (constant, default),
        ``"ct"`` (constant + trend), ``"n"`` (none).
    cols : list of str, optional
        Variable names for display.  Auto-generated if None.
    """

    def __init__(self, data, p, d_max=None, trend="c", cols=None):
        y = _clean_2d(data)
        k = y.shape[1]
        if k < 2:
            raise ValueError(
                f"data must have at least 2 variables (k >= 2), got k = {k}"
            )

        if p < 1:
            raise ValueError(f"p must be >= 1, got {p}")
        if d_max is not None and d_max not in (0, 1, 2):
            raise ValueError(f"d_max must be 0, 1, or 2, got {d_max}")
        if trend not in _VALID_TRENDS:
            raise ValueError(
                f"trend must be one of {sorted(_VALID_TRENDS)}, got {trend!r}"
            )

        if cols is not None:
            if len(cols) != k:
                raise ValueError(
                    f"cols length ({len(cols)}) must match number of variables ({k})"
                )
            self.cols = list(cols)
        else:
            self.cols = [f"y{i}" for i in range(k)]

        self.data = y
        self.p = p
        self.d_max = d_max
        self.trend = trend
        self.result_: TodaYamamotoTestResult | None = None

    def _detect_dmax(self):
        """Determine the maximum order of integration via ADF tests.

        Tests each variable in levels; if unit root is not rejected,
        tests first differences.  Continues up to *d_max* = 2.

        The internal 10% threshold intentionally errs on the side of
        over-specifying the augmentation order.

        Returns
        -------
        int
            Maximum order of integration across all variables.
        """
        from statsmodels.tsa.stattools import adfuller

        k = self.data.shape[1]
        max_d = 0
        for j in range(k):
            series = self.data[:, j]
            d_i = 0
            # Test levels
            adf_pv = adfuller(series, autolag="AIC")[1]
            if adf_pv > _AUTO_DMAX_ALPHA:
                d_i = 1
                # Test first differences
                diff1 = np.diff(series)
                if len(diff1) >= 10:
                    adf_pv_d1 = adfuller(diff1, autolag="AIC")[1]
                    if adf_pv_d1 > _AUTO_DMAX_ALPHA:
                        d_i = 2
            max_d = max(max_d, d_i)
        return max_d

    def fit(self):
        """Execute the Toda-Yamamoto Granger causality test.

        Returns
        -------
        TodaYamamotoTestResult
        """
        from statsmodels.tsa.vector_ar.var_model import VAR as _SM_VAR

        d_max = self.d_max if self.d_max is not None else self._detect_dmax()
        total_lags = self.p + d_max
        k = self.data.shape[1]

        min_obs = total_lags + 10
        if self.data.shape[0] < min_obs:
            raise ValueError(
                f"Need at least {min_obs} observations "
                f"({total_lags} lags + 10), got {self.data.shape[0]}"
            )

        # 1. Estimate VAR(p + d_max)
        sm_var = _SM_VAR(self.data)
        fitted = sm_var.fit(maxlags=total_lags, trend=self.trend, ic=None)

        # 2. Extract coefficient vector and covariance matrix
        all_params = np.asarray(fitted.params)  # shape (n_regressors, k)
        cov_full = np.asarray(
            fitted.cov_params()
        )  # (n_regressors * k,) x (n_regressors * k,)
        resid = np.asarray(fitted.resid)
        nobs = int(fitted.nobs)

        # Parameter layout (n_regressors rows, k cols):
        # [const (if trend), trend (if ct),
        #  L1.y0, L1.y1, ..., L1.y_{k-1}, L2.y0, ...]

        has_const = self.trend != "n"
        has_trend = self.trend == "ct"
        n_det = int(has_const) + int(has_trend)

        # 3. Build test entries
        entries = []
        for eq_idx in range(k):  # caused
            caused_name = self.cols[eq_idx]

            for causing_idx in range(k):
                if causing_idx == eq_idx:
                    continue

                causing_name = [self.cols[causing_idx]]
                wald, p_val = _wald_test_single(
                    all_params,
                    cov_full,
                    k,
                    eq_idx,
                    causing_idx,
                    n_det,
                    self.p,
                )

                entries.append(
                    _TYEntry(
                        test_statistic=float(wald),
                        p_value=float(p_val),
                        df=self.p,
                        caused=caused_name,
                        causing=causing_name,
                    )
                )

            # Joint ALL test
            other_idx = [j for j in range(k) if j != eq_idx]
            if len(other_idx) > 1:
                wald, p_val = _wald_test_multi(
                    all_params,
                    cov_full,
                    k,
                    eq_idx,
                    other_idx,
                    n_det,
                    self.p,
                )
                entries.append(
                    _TYEntry(
                        test_statistic=float(wald),
                        p_value=float(p_val),
                        df=self.p * len(other_idx),
                        caused=caused_name,
                        causing=["ALL"],
                    )
                )

        result = TodaYamamotoTestResult(
            lags=total_lags,
            nobs=nobs,
            residuals=resid,
            tests=entries,
            p=self.p,
            d_max=d_max,
            k=k,
            cols=list(self.cols),
        )
        self.result_ = result
        return result


def _compute_wald(R, param_vec, cov_full, df):
    """Compute Wald statistic and p-value from restriction matrix.

    W = (R * beta)' * (R * cov * R')^{-1} * (R * beta)  ~ chi2(df).

    Parameters
    ----------
    R : np.ndarray
        Restriction matrix, shape (n_restrictions, n_params).
    param_vec : np.ndarray
        Flattened parameter vector, shape (n_params,).
    cov_full : np.ndarray
        Parameter covariance matrix, shape (n_params, n_params).
    df : int
        Degrees of freedom.

    Returns
    -------
    wald : float
    p_value : float
    """
    R_beta = R @ param_vec
    R_cov_Rt = R @ cov_full @ R.T
    try:
        wald = float(R_beta.T @ np.linalg.solve(R_cov_Rt, R_beta))
    except np.linalg.LinAlgError as exc:
        raise RuntimeError(
            "Wald test covariance is singular; causality statistic is undefined"
        ) from exc
    p_value = float(1.0 - scipy_stats.chi2.cdf(wald, df))
    return wald, p_value


def _build_restriction_matrix(n_regressors, k, eq_idx, causing_indices, n_det, p_lags):
    """Build the restriction matrix R for Wald testing.

    R selects the coefficients of the first *p_lags* lags of
    *causing_indices* in the equation for *eq_idx*.

    Parameters
    ----------
    n_regressors : int
        Number of regressors per equation.
    k : int
        Number of endogenous variables.
    eq_idx : int
        Equation index (caused variable).
    causing_indices : list of int
        Causing variable indices.
    n_det : int
        Number of deterministic regressors at the start.
    p_lags : int
        Number of lags to restrict.

    Returns
    -------
    R : np.ndarray
        Restriction matrix, shape (n_restrictions, n_regressors * k).
    """
    n_restrictions = p_lags * len(causing_indices)
    R = np.zeros((n_restrictions, n_regressors * k))
    row = 0
    for lag in range(p_lags):
        for cj in causing_indices:
            row_in_coefs = n_det + lag * k + cj
            col_in_flat = row_in_coefs * k + eq_idx
            R[row, col_in_flat] = 1.0
            row += 1
    return R


def _wald_test_single(all_params, cov_full, k, eq_idx, causing_idx, n_det, p_lags):
    """Wald test: a single causing variable does not Granger-cause caused.

    H0: The first *p_lags* lags of *causing_idx* are zero in the
    equation for *eq_idx*.
    """
    n_regressors = all_params.shape[0]
    param_vec = all_params.ravel()
    R = _build_restriction_matrix(
        n_regressors,
        k,
        eq_idx,
        [causing_idx],
        n_det,
        p_lags,
    )
    return _compute_wald(R, param_vec, cov_full, p_lags)


def _wald_test_multi(all_params, cov_full, k, eq_idx, causing_idx_list, n_det, p_lags):
    """Wald test: multiple causing variables jointly do not Granger-cause.

    H0: The first *p_lags* lags of all variables in *causing_idx_list*
    are zero in the equation for *eq_idx*.
    """
    n_regressors = all_params.shape[0]
    param_vec = all_params.ravel()
    n_restrictions = p_lags * len(causing_idx_list)
    R = _build_restriction_matrix(
        n_regressors,
        k,
        eq_idx,
        causing_idx_list,
        n_det,
        p_lags,
    )
    return _compute_wald(R, param_vec, cov_full, n_restrictions)
