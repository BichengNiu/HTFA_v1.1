"""Engle's Lagrange Multiplier (ARCH-LM) test for ARCH effects.

Reference
--------
Engle, R. F. (1982). "Autoregressive Conditional Heteroscedasticity with
Estimates of the Variance of United Kingdom Inflation." *Econometrica*,
50(4), 987–1007.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats as scipy_stats

from ._base import BaseTest, BaseTestResult
from ._utils import _as_1d_float


def _run_aux_regression(y, X):
    """Run OLS regression: y on X.

    Parameters
    ----------
    y : np.ndarray
        Dependent variable (1-D).
    X : np.ndarray
        Regressor matrix (2-D).

    Returns
    -------
    tuple
        ``(coefficients, residuals, ssr)``.
    """
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    residuals = y - X @ coef
    ssr = float(residuals.T @ residuals)
    return coef, residuals, ssr


@dataclass
class EngleLMTestResult(BaseTestResult):
    """Container for Engle LM test results.

    Additional fields beyond :class:`BaseTestResult`:

    - ``statistic`` — LM = n * R^2 (chi-squared distributed under H0).
    - ``f_statistic`` — F-statistic from the auxiliary regression.
    - ``f_pvalue`` — p-value from the F distribution.
    - ``rsquared`` — R-squared of the auxiliary regression.
    """

    f_statistic: float = 0.0
    f_pvalue: float = 0.0
    rsquared: float = 0.0
    individual_lags: np.ndarray | None = None
    individual_stats: np.ndarray | None = None
    individual_pvalues: np.ndarray | None = None

    def __str__(self) -> str:
        reject = self.pvalue < 0.05 if self.pvalue is not None else False
        conclusion = (
            "Reject H0 (ARCH effects present)"
            if reject
            else "Cannot reject H0 (no ARCH effects)"
        )

        lines = [
            self._format_conclusion("Engle LM Test", "No ARCH effects"),
            f"  F-statistic         : {self.f_statistic:.3f}",
            f"  F p-value           : {self.f_pvalue:.4f}",
            f"  R-squared           : {self.rsquared:.4f}",
            f"  Effective obs.      : {self.nobs}",
            f"  Conclusion (5%): {conclusion}",
        ]

        # Per-lag breakdown
        if (
            self.individual_lags is not None
            and self.individual_stats is not None
            and self.individual_pvalues is not None
        ):
            lines.append("")
            lines.append("Per-Lag Breakdown")
            lines.append("-" * 50)
            lines.append(
                f"{'Lag':<6} {'LM (n.R-squared)':<18} {'df':<6} {'p-value':<10}"
            )
            lines.append("-" * 50)
            for i in range(len(self.individual_lags)):
                lag = self.individual_lags[i]
                lm = self.individual_stats[i]
                pv = self.individual_pvalues[i]
                lines.append(f"{lag:<6} {lm:<18.3f} {lag:<6} {pv:<10.4f}")

        return "\n".join(lines)


class EngleLMTest(BaseTest):
    """Engle's Lagrange Multiplier test for ARCH effects.

    The test regresses squared residuals on their own lags and uses
    LM = n * R^2 ~ chi^2(p) as the test statistic.

    Parameters
    ----------
    data : array-like
        Time series to test (e.g., returns). If *residuals* is not provided,
        residuals are obtained by de-meaning *y*.
    lags : int, optional
        Number of lagged squared residuals in the auxiliary regression.
        Default is 10.
    residuals : array-like, optional
        Pre-computed residuals. If ``None``, residuals are computed as
        ``y - mean(y)``.

    Attributes
    ----------
    result_ : EngleLMTestResult
        Full test results after calling :meth:`fit`.
    """

    def __init__(
        self,
        data,
        lags: int = 10,
        residuals=None,
    ):
        raw_data = _as_1d_float(data)
        if np.any(np.isinf(raw_data)):
            raise ValueError("data must not contain infinite values")
        valid_rows = ~np.isnan(raw_data)
        y_arr = raw_data[valid_rows]

        if lags < 1:
            raise ValueError(f"lags must be >= 1, got {lags}")

        if len(y_arr) <= 2 * lags + 1:
            raise ValueError(
                f"Need at least {2 * lags + 2} observations for {lags} lags, "
                f"got {len(y_arr)}"
            )

        self.data = y_arr
        self.lags = lags

        if residuals is not None:
            residuals_arr = _as_1d_float(residuals, name="residuals")
            if residuals_arr.shape != raw_data.shape:
                raise ValueError(
                    f"residuals has {len(residuals_arr)} obs but y has {len(raw_data)}"
                )
            residuals_arr = residuals_arr[valid_rows]
            if not np.all(np.isfinite(residuals_arr)):
                raise ValueError("residuals must contain only finite values")
            self.residuals = residuals_arr
        else:
            self.residuals = y_arr - np.mean(y_arr)

        self.result_: EngleLMTestResult | None = None

    def fit(self) -> EngleLMTestResult:
        """Run the Engle LM test for ARCH effects.

        Returns
        -------
        EngleLMTestResult
        """
        e = self.residuals
        e2 = e**2
        T = len(e2)
        p = self.lags

        # Build auxiliary regression: e2[t] on [1, e2[t-1], ..., e2[t-p]]
        n_eff = T - p
        y_dep = e2[p:]  # dependent variable: e2[t] for t = p+1 .. T

        X = np.ones((n_eff, p + 1))
        for j in range(1, p + 1):
            X[:, j] = e2[p - j : T - j]

        # OLS auxiliary regression
        _, _resid_aux, ssr = _run_aux_regression(y_dep, X)
        sst = np.sum((y_dep - np.mean(y_dep)) ** 2)
        r_squared = 1.0 - ssr / sst if sst > 0 else 0.0

        # LM statistic
        lm_stat = n_eff * r_squared
        lm_pval = 1.0 - scipy_stats.chi2.cdf(lm_stat, p)

        # F-statistic: ( (SST-SSR)/p ) / ( SSR/(n-p-1) )
        ssr_restricted = sst  # SST under H0 (all slope coefs = 0)
        if sst == 0:
            f_stat = np.nan
            f_pval = np.nan
        else:
            f_stat = ((ssr_restricted - ssr) / p) / (ssr / (n_eff - p - 1))
            f_pval = 1.0 - scipy_stats.f.cdf(f_stat, p, n_eff - p - 1)

        # Per-lag: run auxiliary regression for k = 1, 2, ..., p
        ind_lags = np.arange(1, p + 1, dtype=int)
        ind_stats = np.empty(p)
        ind_pvalues = np.empty(p)
        for k in range(1, p):
            nk = T - k
            yk = e2[k:]
            Xk = np.ones((nk, k + 1))
            for j in range(1, k + 1):
                Xk[:, j] = e2[k - j : T - j]
            _, _, ssr_k = _run_aux_regression(yk, Xk)
            sst_k = np.sum((yk - np.mean(yk)) ** 2)
            r2_k = 1.0 - ssr_k / sst_k if sst_k > 0 else 0.0
            lm_k = nk * r2_k
            pval_k = 1.0 - scipy_stats.chi2.cdf(lm_k, k)
            ind_stats[k - 1] = lm_k
            ind_pvalues[k - 1] = pval_k
        ind_stats[-1] = lm_stat
        ind_pvalues[-1] = lm_pval

        self.result_ = EngleLMTestResult(
            statistic=lm_stat,
            pvalue=lm_pval,
            lags=p,
            nobs=n_eff,
            residuals=e,
            f_statistic=f_stat,
            f_pvalue=f_pval,
            rsquared=r_squared,
            individual_lags=ind_lags,
            individual_stats=ind_stats,
            individual_pvalues=ind_pvalues,
        )
        return self.result_
