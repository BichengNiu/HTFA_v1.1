"""Augmented Dickey-Fuller (ADF) unit root test.

Wraps :func:`statsmodels.tsa.stattools.adfuller` in the TsTests
:class:`BaseTest` / :class:`BaseTestResult` framework.

Reference
---------
Dickey, D. A. & Fuller, W. A. (1979). "Distribution of the Estimators
for Autoregressive Time Series with a Unit Root." *JASA*, 74(366), 427–431.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._base import BaseTest, BaseTestResult
from ._utils import _clean_1d
from ._unitroot_plot import _render_critical_value_plot


@dataclass
class ADFTestResult(BaseTestResult):
    """Container for Augmented Dickey-Fuller (ADF) test results.

    In addition to the fields inherited from :class:`BaseTestResult`:

    Parameters
    ----------
    trend : str
        Trend specification used (``"c"``, ``"ct"``, ``"ctt"``, ``"n"``).
    critical_values : dict
        Critical values keyed by significance level (e.g. ``"1%"``).
    max_lag : int or None
        Maximum lag considered during automatic selection.
    icbest : float or None
        Best information criterion value (if auto-selected).
    """

    trend: str = "c"
    critical_values: dict = field(default_factory=dict)
    max_lag: int | None = None
    icbest: float | None = None

    def __str__(self) -> str:
        # Determine rejection
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
            self._format_conclusion("ADF Test", "Unit root (non-stationary)"),
            f"  Trend              : {self.trend}",
        ]
        if self.max_lag is not None:
            lines.append(f"  Max lags (auto)    : {self.max_lag}")
        if self.icbest is not None:
            lines.append(f"  IC best            : {self.icbest:.4f}")
        lines += [
            f"  Observations       : {self.nobs}",
            f"  Conclusion (5%): {conclusion}",
        ]

        return "\n".join(lines)

    def plot_test(self, ax=None):
        """Plot the ADF test statistic against critical values.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        return _render_critical_value_plot(self, "ADF", ax)


class ADFTest(BaseTest):
    """Augmented Dickey-Fuller (ADF) unit root test.

    Wraps :func:`statsmodels.tsa.stattools.adfuller`.

    H0: The series has a unit root (is non-stationary).
    H1: The series is stationary (no unit root).

    Parameters
    ----------
    data : array-like
        The time series to test.
    trend : str, optional
        Trend specification: ``"c"`` (constant, default), ``"ct"``
        (constant + trend), ``"ctt"`` (constant + quadratic trend),
        or ``"n"`` (none).
    max_lags : int, optional
        Maximum number of lags for automatic selection. If *lags* is
        also provided, *max_lags* is ignored. Default 8.
    lags : int, optional
        Fixed number of lags. If ``None`` (default), automatic selection
        via AIC is performed.
    autolag : str, optional
        Criterion for automatic lag selection: ``"AIC"`` (default),
        ``"BIC"``, or ``"t-stat"``.

    Attributes
    ----------
    result_ : ADFTestResult
        Full test results after calling :meth:`fit`.
    """

    def __init__(
        self,
        data,
        trend: str = "c",
        max_lags: int = 8,
        lags: int | None = None,
        autolag: str = "AIC",
    ):
        self.data = _clean_1d(data)
        if trend not in ("c", "ct", "ctt", "n"):
            raise ValueError(f"trend must be 'c', 'ct', 'ctt', or 'n', got {trend!r}")
        self.trend = trend
        self.max_lags = max_lags
        self.lags = lags
        if autolag not in ("AIC", "BIC", "t-stat"):
            raise ValueError(
                f"autolag must be 'AIC', 'BIC', or 't-stat', got {autolag!r}"
            )
        self.autolag = autolag
        self.result_: ADFTestResult | None = None

    def fit(self) -> ADFTestResult:
        """Run the ADF test.

        Returns
        -------
        ADFTestResult
        """
        from statsmodels.tsa.stattools import adfuller

        kwargs = {
            "regression": self.trend,
            "autolag": self.autolag,
        }
        if self.lags is not None:
            kwargs["maxlag"] = self.lags
        else:
            kwargs["maxlag"] = self.max_lags

        adf_result = adfuller(self.data, **kwargs)

        statistic = float(adf_result[0])
        pvalue = float(adf_result[1])
        used_lag = int(adf_result[2])
        nobs = int(adf_result[3])
        crit_vals = {str(k): float(v) for k, v in adf_result[4].items()}

        # icbest is at index 5 if available
        icbest = None
        if len(adf_result) > 5 and adf_result[5] is not None:
            icbest = float(adf_result[5])

        self.result_ = ADFTestResult(
            statistic=statistic,
            pvalue=pvalue,
            lags=used_lag,
            nobs=nobs,
            trend=self.trend,
            critical_values=crit_vals,
            max_lag=self.max_lags if self.lags is None else None,
            icbest=icbest,
        )
        return self.result_
