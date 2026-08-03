"""Ts — Time Series Econometrics Toolkit.

This package consolidates six sub-packages under a unified namespace.

- :mod:`Ts.TsPlots`  — shared plotting (series, scatter, ACF/PACF)
- :mod:`Ts.TsSims`   — synthetic data generation (SARIMA, GARCH, TS/DS)
- :mod:`Ts.TsUtils`  — preprocessing (STL, missing-value interpolation)
- :mod:`Ts.TsModels` — model estimation (SARIMA, GARCH)
- :mod:`Ts.TsMetrics` — forecast metrics and leakage-free evaluation
- :mod:`Ts.TsTests`  — statistical tests (unit root, structural break, ARCH)

Quick start
-----------
>>> from Ts import STL, interpolate_missing, SARIMA, AutoSARIMA, ADFTest
>>> from Ts.TsPlots import plot_series, plot_scatter, plot_acf, plot_pacf
>>> from Ts.TsSims import simulate_sarima, simulate_garch
>>> from Ts.TsUtils import STL, interpolate_missing
>>> from Ts.TsModels import SARIMA, GARCH, AutoSARIMA, AutoGARCH
>>> from Ts.TsMetrics import rmse, oos, backtest, compare_forecasts
>>> from Ts.TsTests import ADFTest, KPSSTest, LjungBoxTest
"""

# ---------------------------------------------------------------------------
# TsPlots — plotting
# ---------------------------------------------------------------------------
from .TsPlots import plot_series, plot_scatter, plot_acf, plot_pacf

# ---------------------------------------------------------------------------
# TsUtils — preprocessing
# ---------------------------------------------------------------------------
from .TsUtils import (
    InterpolationResult,
    STL,
    STLResult,
    TimeSeriesSummary,
    difference,
    interpolate_missing,
)

# ---------------------------------------------------------------------------
# TsSims — simulation
# ---------------------------------------------------------------------------
from .TsSims import (
    BaseSimResult,
    SimSARIMAResult,
    SimGARCHResult,
    SimTSDSResult,
    simulate_sarima,
    simulate_garch,
    simulate_igarch,
    simulate_gjr_garch,
    simulate_egarch,
    simulate_garch_m,
    simulate_trend_stationary,
    simulate_difference_stationary,
)

# ---------------------------------------------------------------------------
# TsModels — estimation
# ---------------------------------------------------------------------------
from .TsModels import (
    BaseModel,
    BaseModelResult,
    ResidualTestResults,
    SARIMA,
    ScenarioForecastResult,
    EventSpec,
    PolicyEffectResult,
    GARCH,
    AutoSARIMA,
    AutoGARCH,
    AutoModelResult,
    compare_models,
)

from .TsMetrics import (
    BacktestResult,
    ComparisonResult,
    OOSResult,
    backtest,
    compare_forecasts,
    compute_metrics,
    mae,
    mape,
    mse,
    oos,
    rmse,
    smape,
    theil_u1,
)

# ---------------------------------------------------------------------------
# TsTests — statistical tests
# ---------------------------------------------------------------------------
from .TsTests import (
    BaseTest,
    BaseTestResult,
    # Unit root tests
    ADFTest,
    ADFTestResult,
    PhillipsPerronTest,
    PhillipsPerronTestResult,
    KPSSTest,
    KPSSTestResult,
    # Structural break tests
    PerronTest,
    PerronTestResult,
    ZivotAndrewsTest,
    ZivotAndrewsTestResult,
    # ARCH-effect tests
    LjungBoxTest,
    LjungBoxTestResult,
    EngleLMTest,
    EngleLMTestResult,
    # Normality test
    NormalityTest,
    NormalityTestResult,
)

__all__ = [  # noqa: RUF022 - public API is grouped by subpackage
    # TsPlots
    "plot_series",
    "plot_scatter",
    "plot_acf",
    "plot_pacf",
    # TsUtils
    "STL",
    "STLResult",
    "TimeSeriesSummary",
    "difference",
    "interpolate_missing",
    "InterpolationResult",
    # TsSims — base
    "BaseSimResult",
    # TsSims — result classes
    "SimSARIMAResult",
    "SimGARCHResult",
    "SimTSDSResult",
    # TsSims — functions
    "simulate_sarima",
    "simulate_garch",
    "simulate_igarch",
    "simulate_gjr_garch",
    "simulate_egarch",
    "simulate_garch_m",
    "simulate_trend_stationary",
    "simulate_difference_stationary",
    # TsModels — base
    "BaseModel",
    "BaseModelResult",
    "ResidualTestResults",
    # TsModels — models
    "SARIMA",
    "ScenarioForecastResult",
    "EventSpec",
    "PolicyEffectResult",
    "GARCH",
    "AutoSARIMA",
    "AutoGARCH",
    "AutoModelResult",
    # TsModels — utilities
    "compare_models",
    # TsMetrics
    "mae",
    "mse",
    "rmse",
    "mape",
    "smape",
    "theil_u1",
    "compute_metrics",
    "oos",
    "backtest",
    "compare_forecasts",
    "OOSResult",
    "BacktestResult",
    "ComparisonResult",
    # TsTests — base
    "BaseTest",
    "BaseTestResult",
    # TsTests — unit root
    "ADFTest",
    "ADFTestResult",
    "PhillipsPerronTest",
    "PhillipsPerronTestResult",
    "KPSSTest",
    "KPSSTestResult",
    # TsTests — structural break
    "PerronTest",
    "PerronTestResult",
    "ZivotAndrewsTest",
    "ZivotAndrewsTestResult",
    # TsTests — ARCH-effects
    "LjungBoxTest",
    "LjungBoxTestResult",
    "EngleLMTest",
    "EngleLMTestResult",
    # TsTests — normality
    "NormalityTest",
    "NormalityTestResult",
]
