"""Forecast performance metrics and leakage-free evaluation tools.

``TsMetrics`` owns point-forecast metrics, honest holdout evaluation,
rolling-origin backtesting, and comparison of evaluation results. Model
estimation and forecast generation remain in :mod:`Ts.TsModels`.
"""

from ._backtest import backtest
from ._compare import compare_forecasts
from ._metrics import (
    compute_metrics,
    mae,
    mape,
    mse,
    rmse,
    smape,
    theil_u1,
)
from ._oos import oos
from ._results import BacktestResult, ComparisonResult, OOSResult

__all__ = [
    "BacktestResult",
    "ComparisonResult",
    "OOSResult",
    "backtest",
    "compare_forecasts",
    "compute_metrics",
    "mae",
    "mape",
    "mse",
    "oos",
    "rmse",
    "smape",
    "theil_u1",
]
