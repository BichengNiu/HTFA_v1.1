"""Base classes for all statistical tests in TsTests.

Provides:

- :class:`BaseTestResult` — minimal common result container (dataclass).
- :class:`BaseTest` — abstract base class enforcing the ``fit()`` / ``summary()``
  / ``result_`` contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class BaseTestResult:
    """Minimal common result container for all TsTests test results.

    Subclasses add test-specific fields (critical values, coefficients, etc.).

    Parameters
    ----------
    statistic : float
        Test statistic value.
    pvalue : float or None
        p-value of the test. May be ``None`` for tests that use critical-value
        comparison (e.g., Perron, Zivot-Andrews).
    lags : int
        Number of lags used in the test.
    nobs : int
        Effective number of observations.
    residuals : np.ndarray or None
        Residual series from the test regression, if applicable.
    """

    statistic: float
    pvalue: float | None
    lags: int
    nobs: int
    residuals: np.ndarray | None = None

    def _format_conclusion(self, stat_name: str, h0_desc: str) -> str:
        """Generate standardized test header.

        Produces lines with the test name, statistic, p-value, lags,
        and null-hypothesis description. Each subclass appends its own
        conclusion text after the header.

        Parameters
        ----------
        stat_name : str
            Display name for the test (e.g. ``"ADF Test"``).
        h0_desc : str
            Description of the null hypothesis (e.g. ``"Unit root"``).

        Returns
        -------
        str
            Multi-line header string.
        """
        lines = [
            "=" * 50,
            f"  {stat_name}",
            "=" * 50,
        ]
        if self.pvalue is not None:
            lines.append(f"  Test Statistic: {self.statistic:.6f}")
            lines.append(f"  P-value:        {self.pvalue:.6f}")
        else:
            lines.append(f"  Test Statistic: {self.statistic:.6f}")
            critical_values = getattr(self, "critical_values", None)
            if critical_values:
                lines.append("  Critical Values:")
                for k, v in sorted(critical_values.items()):
                    lines.append(f"    {k}: {v:.4f}")
        lines.append(f"  Lags:           {self.lags}")
        lines.append(f"  H0: {h0_desc}")
        return "\n".join(lines)


@dataclass
class BaseMultiTestResult:
    """Common metadata for tests that return multiple directional results."""

    lags: int
    nobs: int
    residuals: np.ndarray | None = None


class BaseTest(ABC):
    """Abstract base class for all statistical tests in TsTests.

    Every test must implement :meth:`fit` and expose a :attr:`result_`
    attribute. The :meth:`summary` method returns a formatted string
    representation (no side effects — does not print).
    """

    result_: BaseTestResult | BaseMultiTestResult | None = None

    @abstractmethod
    def fit(self) -> BaseTestResult | BaseMultiTestResult:
        """Execute the test and return a result object.

        The result is also stored in :attr:`result_`.
        """
        ...

    def summary(self) -> str:
        """Return a formatted summary string for the test results.

        Does **not** print — the caller decides how to display.
        """
        if self.result_ is None:
            self.fit()
        return str(self.result_)
