"""Jarque-Bera normality test.

Reference
--------
Jarque, C. M. & Bera, A. K. (1987). "A Test for Normality of Observations
and Regression Residuals." *International Statistical Review*, 55(2), 163-172.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats as scipy_stats

from ._base import BaseTest, BaseTestResult
from ._utils import _clean_1d


@dataclass
class NormalityTestResult(BaseTestResult):
    """Container for Jarque-Bera normality test results.

    Additional fields beyond :class:`BaseTestResult`:

    - ``skewness`` --- sample skewness.
    - ``kurtosis`` --- sample excess kurtosis.
    """

    skewness: float = 0.0
    kurtosis: float = 0.0

    def __str__(self) -> str:
        reject = self.pvalue < 0.05 if self.pvalue is not None else False
        conclusion = (
            "Reject H0 (not normally distributed)"
            if reject
            else "Cannot reject H0 (normally distributed)"
        )

        lines = [
            self._format_conclusion(
                "Jarque-Bera Normality Test", "Normal distribution"
            ),
            f"  Skewness            : {self.skewness:.4f}",
            f"  Kurtosis            : {self.kurtosis:.4f}",
            f"  Effective obs.      : {self.nobs}",
            f"  Conclusion (5%): {conclusion}",
        ]
        return "\n".join(lines)

    def plot_test(self):
        """Plot a histogram with normal curve overlay for the test data.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        import matplotlib.pyplot as plt
        from Ts.TsPlots.style import DEFAULT_PALETTE, style_axes, FIGSIZE

        fig, ax = plt.subplots(figsize=FIGSIZE)
        if self.residuals is not None and len(self.residuals) > 0:
            ax.hist(
                self.residuals,
                bins="auto",
                density=True,
                alpha=0.7,
                color=DEFAULT_PALETTE[0],
            )
            from scipy import stats as scipy_stats

            x = np.linspace(self.residuals.min(), self.residuals.max(), 100)
            ax.plot(
                x,
                scipy_stats.norm.pdf(
                    x, np.mean(self.residuals), np.std(self.residuals)
                ),
                color=DEFAULT_PALETTE[3],
                linewidth=2,
            )
        ax.set_title(
            f"Jarque-Bera Test: statistic={self.statistic:.3f}, "
            f"p-value={self.pvalue:.4f}"
        )
        style_axes(ax, grid=False)
        fig.tight_layout(pad=1.5)
        return fig, ax


class NormalityTest(BaseTest):
    """Jarque-Bera test for normality.

    Tests H0: the data are drawn from a normal distribution.
    The JB statistic is asymptotically chi-squared(2) under H0.

    Parameters
    ----------
    data : array-like
        Time series (or residuals) to test. Must have at least 8 observations.

    Attributes
    ----------
    result_ : NormalityTestResult
        Full test results after calling :meth:`fit`.
    """

    def __init__(self, data):
        y_arr = _clean_1d(data)

        if len(y_arr) < 8:
            raise ValueError(f"Need at least 8 observations, got {len(y_arr)}")

        self.data = y_arr
        self.result_: NormalityTestResult | None = None

    def fit(self) -> NormalityTestResult:
        """Run the Jarque-Bera normality test.

        Returns
        -------
        NormalityTestResult
        """
        skew = float(scipy_stats.skew(self.data))
        kurt = float(scipy_stats.kurtosis(self.data))  # excess kurtosis
        n = len(self.data)

        jb_stat = n / 6.0 * (skew**2 + kurt**2 / 4.0)
        jb_pval = float(scipy_stats.chi2.sf(jb_stat, 2))

        self.result_ = NormalityTestResult(
            statistic=jb_stat,
            pvalue=jb_pval,
            lags=0,
            nobs=n,
            residuals=self.data.copy(),
            skewness=skew,
            kurtosis=kurt,
        )
        return self.result_
