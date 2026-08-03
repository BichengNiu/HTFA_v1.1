"""TsTests — Time series statistical tests.

This package implements statistical tests for time series analysis:

**Unit root tests**

- :class:`ADFTest` — Augmented Dickey-Fuller unit root test.
- :class:`PhillipsPerronTest` — Phillips-Perron unit root test.
- :class:`KPSSTest` — KPSS stationarity test (H0: stationary).

**Structural break unit root tests**

- :class:`PerronTest` — Perron (1989) test with a *known* break date.
- :class:`ZivotAndrewsTest` — Zivot & Andrews (1992) test with an
  *unknown* break date (endogenously selected).

**ARCH-effect tests**

- :class:`LjungBoxTest` — Ljung-Box Q-test on squared data for ARCH effects.
- :class:`EngleLMTest` — Engle's Lagrange Multiplier test for ARCH effects.

**Granger causality tests**

- :class:`TodaYamamotoTest` — Toda-Yamamoto (1995) Granger causality test
  for possibly integrated or cointegrated VAR systems.

Quick start
-----------
>>> from Ts.TsTests import (
...     ADFTest, PhillipsPerronTest, KPSSTest,
...     PerronTest, ZivotAndrewsTest, LjungBoxTest, EngleLMTest,
... )

>>> # ADF test
>>> adf = ADFTest(y, trend="c")
>>> print(adf.summary())

>>> # KPSS test
>>> kpss = KPSSTest(y, trend="c")
>>> kpss.result_.plot_test()
"""

from ._base import BaseMultiTestResult, BaseTest, BaseTestResult
from ._perron import PerronTest, PerronTestResult
from ._zivot import ZivotAndrewsTest, ZivotAndrewsTestResult
from ._ljungbox import LjungBoxTest, LjungBoxTestResult
from ._engle_lm import EngleLMTest, EngleLMTestResult
from ._normality import NormalityTest, NormalityTestResult
from ._adf import ADFTest, ADFTestResult
from ._phillips_perron import PhillipsPerronTest, PhillipsPerronTestResult
from ._kpss import KPSSTest, KPSSTestResult
from ._johansen import JohansenTest, JohansenTestResult
from ._toda_yamamoto import TodaYamamotoTest, TodaYamamotoTestResult

__all__ = [
    # Unit root tests
    "ADFTest",
    "ADFTestResult",
    "BaseMultiTestResult",
    # Base classes
    "BaseTest",
    "BaseTestResult",
    "EngleLMTest",
    "EngleLMTestResult",
    "JohansenTest",
    "JohansenTestResult",
    "KPSSTest",
    "KPSSTestResult",
    # ARCH-effect tests
    "LjungBoxTest",
    "LjungBoxTestResult",
    # Normality test
    "NormalityTest",
    "NormalityTestResult",
    # Structural break tests
    "PerronTest",
    # Result containers
    "PerronTestResult",
    "PhillipsPerronTest",
    "PhillipsPerronTestResult",
    "TodaYamamotoTest",
    "TodaYamamotoTestResult",
    "ZivotAndrewsTest",
    "ZivotAndrewsTestResult",
]
