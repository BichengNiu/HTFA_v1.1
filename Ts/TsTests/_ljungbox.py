"""Ljung-Box portmanteau test for autocorrelation and ARCH effects.

Reference
--------
Ljung, G. M. & Box, G. E. P. (1978). "On a Measure of Lack of Fit in Time
Series Models." *Biometrika*, 65(2), 297–303.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from statsmodels.stats.diagnostic import acorr_ljungbox

from ._base import BaseTest, BaseTestResult
from ._utils import _clean_1d


@dataclass
class LjungBoxTestResult(BaseTestResult):
    """Container for Ljung-Box Q-test results.

    Additional fields beyond :class:`BaseTestResult`:

    - ``individual_lags`` — lag orders tested (1 .. *lags*).
    - ``individual_stats`` — Q statistic at each lag.
    - ``individual_pvalues`` — p-value at each lag.
    - ``apply_squared`` — whether the test was applied to squared data.
    """

    individual_lags: np.ndarray | None = None
    individual_stats: np.ndarray | None = None
    individual_pvalues: np.ndarray | None = None
    apply_squared: bool = True

    def __str__(self) -> str:
        sq_label = " (squared)" if self.apply_squared else ""
        stat_name = f"Ljung-Box Q-Test{sq_label}"

        if self.apply_squared:
            h0_desc = "No ARCH effects"
            conclusion_reject = "Reject H0 (ARCH effects present)"
            conclusion_fail = "Cannot reject H0 (no ARCH effects)"
        else:
            h0_desc = "No autocorrelation"
            conclusion_reject = "Reject H0 (autocorrelation present)"
            conclusion_fail = "Cannot reject H0 (no autocorrelation)"

        reject = self.pvalue < 0.05 if self.pvalue is not None else False
        conclusion = conclusion_reject if reject else conclusion_fail

        lines = [
            self._format_conclusion(stat_name, h0_desc),
            f"  Effective obs.      : {self.nobs}",
            f"  Conclusion (5%): {conclusion}",
        ]
        return "\n".join(lines)


class LjungBoxTest(BaseTest):
    """Ljung-Box Q-test for autocorrelation in raw or squared data.

    When *apply_squared* is ``True`` (the default), the test is applied to
    squared data, which serves as a test for ARCH effects: under the null of
    no ARCH, the squared series is serially uncorrelated.

    Parameters
    ----------
    data : array-like
        Time series (or residuals) to test.
    lags : int, optional
        Number of lags for the Q statistic. Default is 10.
    apply_squared : bool, optional
        If ``True`` (default), test is applied to ``y^2`` (ARCH-effect test).
        If ``False``, test is applied to *y* directly (autocorrelation test).

    Attributes
    ----------
    result_ : LjungBoxTestResult
        Full test results after calling :meth:`fit`.
    """

    def __init__(
        self,
        data,
        lags: int = 10,
        apply_squared: bool = True,
    ):
        y_arr = _clean_1d(data)

        if lags < 1:
            raise ValueError(f"lags must be >= 1, got {lags}")

        if len(y_arr) <= lags + 1:
            raise ValueError(
                f"Need at least {lags + 2} observations for {lags} lags, "
                f"got {len(y_arr)}"
            )

        self.data = y_arr
        self.lags = lags
        self.apply_squared = apply_squared
        self.result_: LjungBoxTestResult | None = None

    def fit(self) -> LjungBoxTestResult:
        """Run the Ljung-Box Q-test.

        Returns
        -------
        LjungBoxTestResult
        """
        y = self.data
        data = y**2 if self.apply_squared else y

        # acorr_ljungbox with a single lag value, return_df=False
        lb_result = acorr_ljungbox(data, lags=self.lags, return_df=True)

        # Extract the Q statistic and p-value at the maximum lag
        q_stat = float(lb_result["lb_stat"].iloc[-1])
        p_val = float(lb_result["lb_pvalue"].iloc[-1])

        # Per-lag values
        ind_lags = np.arange(1, self.lags + 1)
        ind_stats = lb_result["lb_stat"].values.astype(float)
        ind_pvalues = lb_result["lb_pvalue"].values.astype(float)

        self.result_ = LjungBoxTestResult(
            statistic=q_stat,
            pvalue=p_val,
            lags=self.lags,
            nobs=len(data),
            residuals=None,
            individual_lags=ind_lags,
            individual_stats=ind_stats,
            individual_pvalues=ind_pvalues,
            apply_squared=self.apply_squared,
        )
        return self.result_
