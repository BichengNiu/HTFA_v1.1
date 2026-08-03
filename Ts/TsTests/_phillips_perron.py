"""Phillips-Perron (PP) unit root test.

Wraps :class:`arch.unitroot.PhillipsPerron` in the TsTests
:class:`BaseTest` / :class:`BaseTestResult` framework.

Reference
---------
Phillips, P. C. B. & Perron, P. (1988). "Testing for a Unit Root in
Time Series Regression." *Biometrika*, 75(2), 335–346.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._base import BaseTest, BaseTestResult
from ._utils import _clean_1d
from ._unitroot_plot import _render_critical_value_plot


@dataclass
class PhillipsPerronTestResult(BaseTestResult):
    """Container for Phillips-Perron (PP) test results.

    In addition to the fields inherited from :class:`BaseTestResult`:

    Parameters
    ----------
    trend : str
        Trend specification used (``"c"`` or ``"ct"``).
    test_type : str
        Test type: ``"tau"`` (t-statistic, default) or ``"rho"``.
    critical_values : dict
        Critical values keyed by significance level.
    """

    trend: str = "c"
    test_type: str = "tau"
    critical_values: dict = field(default_factory=dict)

    def __str__(self) -> str:
        label = (
            "Phillips-Perron (PP) Z(tau) Test"
            if self.test_type == "tau"
            else "Phillips-Perron (PP) Z(rho) Test"
        )

        if self.pvalue is not None:
            reject = self.pvalue < 0.05
        else:
            cv_5 = self.critical_values.get("5%")
            reject = cv_5 is not None and self.statistic < cv_5

        conclusion = (
            "Reject H0 -> series is stationary"
            if reject
            else "Cannot reject H0 -> series has a unit root"
        )

        lines = [
            self._format_conclusion(label, "Unit root (non-stationary)"),
            f"  Trend              : {self.trend}",
            f"  Lags (NW bandwidth) : {self.lags}",
            f"  Observations       : {self.nobs}",
            f"  Conclusion (5%): {conclusion}",
        ]

        return "\n".join(lines)

    def plot_test(self, ax=None):
        """Plot the PP test statistic against critical values.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        label = "Phillips-Perron"
        return _render_critical_value_plot(self, label, ax)


class PhillipsPerronTest(BaseTest):
    """Phillips-Perron (PP) unit root test.

    Wraps :class:`arch.unitroot.PhillipsPerron`.

    Unlike the ADF test, the PP test uses a non-parametric correction
    (Newey-West) for serial correlation instead of adding lagged
    differences.

    H0: The series has a unit root (is non-stationary).
    H1: The series is stationary (no unit root).

    Parameters
    ----------
    data : array-like
        The time series to test.
    trend : str, optional
        Trend specification: ``"c"`` (constant, default) or ``"ct"``
        (constant + trend).
    lags : int, optional
        Number of Newey-West lags. If ``None`` (default), automatic
        selection is used.
    test_type : str, optional
        ``"tau"`` (t-statistic, default) or ``"rho"`` (coefficient-based).

    Attributes
    ----------
    result_ : PhillipsPerronTestResult
        Full test results after calling :meth:`fit`.
    """

    _VALID_TRENDS = ("c", "ct")
    _VALID_TEST_TYPES = ("tau", "rho")

    def __init__(
        self,
        data,
        trend: str = "c",
        lags: int | None = None,
        test_type: str = "tau",
    ):
        self.data = _clean_1d(data)
        if trend not in self._VALID_TRENDS:
            raise ValueError(f"trend must be {self._VALID_TRENDS}, got {trend!r}")
        self.trend = trend
        self.lags = lags
        if test_type not in self._VALID_TEST_TYPES:
            raise ValueError(
                f"test_type must be {self._VALID_TEST_TYPES}, got {test_type!r}"
            )
        self.test_type = test_type
        self.result_: PhillipsPerronTestResult | None = None

    def fit(self) -> PhillipsPerronTestResult:
        """Run the Phillips-Perron test.

        Returns
        -------
        PhillipsPerronTestResult
        """
        from arch.unitroot import PhillipsPerron

        kwargs = {"trend": self.trend, "test_type": self.test_type}
        if self.lags is not None:
            kwargs["lags"] = self.lags

        pp = PhillipsPerron(self.data, **kwargs)

        statistic = float(pp.stat)
        pvalue = float(pp.pvalue)
        used_lags = int(pp.lags)
        nobs = int(pp.nobs)
        crit_vals = {}
        if hasattr(pp, "critical_values"):
            crit_vals = {str(k): float(v) for k, v in pp.critical_values.items()}

        self.result_ = PhillipsPerronTestResult(
            statistic=statistic,
            pvalue=pvalue,
            lags=used_lags,
            nobs=nobs,
            trend=self.trend,
            test_type=self.test_type,
            critical_values=crit_vals,
        )
        return self.result_
