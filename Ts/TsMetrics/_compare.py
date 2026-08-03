"""Comparison of forecast evaluation results."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ._results import BacktestResult, ComparisonResult, OOSResult

_ERROR_METRICS = frozenset({"mae", "mse", "rmse", "mape", "smape", "theil_u1"})


def _comparison_items(results, metric):
    """Validate the comparison request and return its ordered items."""
    if not isinstance(results, Mapping):
        raise TypeError("results must be a mapping of names to results")
    if not results:
        raise ValueError("results must not be empty")
    if metric not in _ERROR_METRICS:
        raise ValueError(
            f"metric must be one of {sorted(_ERROR_METRICS)}, got {metric!r}"
        )
    return list(results.items())


def _comparison_reference(items):
    """Return the first valid result as the comparison reference."""
    first_name, first = items[0]
    if not isinstance(first, (OOSResult, BacktestResult)):
        raise TypeError(f"result {first_name!r} is not an OOSResult or BacktestResult")
    return first


def _comparable_score(name, result, reference, metric):
    """Validate and score one result against shared reference data."""
    if not isinstance(name, str):
        raise TypeError("result names must be strings")
    if not isinstance(result, type(reference)):
        raise TypeError("all compared results must use the same evaluation method")
    if result.target != reference.target:
        raise ValueError("all compared results must use the same target")
    if isinstance(result, OOSResult):
        for attribute in ("estimation_indices", "validation_indices"):
            if not np.array_equal(
                np.asarray(getattr(result, attribute)),
                np.asarray(getattr(reference, attribute)),
            ):
                raise ValueError(
                    f"all compared OOS results must use the same {attribute}"
                )
        for attribute in ("estimation_dates", "validation_dates"):
            result_dates = getattr(result, attribute)
            reference_dates = getattr(reference, attribute)
            if (result_dates is None) != (reference_dates is None):
                raise ValueError(
                    "all compared OOS results must use the same date metadata"
                )
            if result_dates is not None and not result_dates.equals(reference_dates):
                raise ValueError(
                    f"all compared OOS results must use the same {attribute}"
                )
    elif not np.array_equal(
        np.asarray(result.target_indices),
        np.asarray(reference.target_indices),
    ):
        raise ValueError("all compared backtests must use the same target indices")
    result_actual = np.asarray(result.actual)
    reference_actual = np.asarray(reference.actual)
    if result_actual.shape != reference_actual.shape or not np.array_equal(
        result_actual,
        reference_actual,
        equal_nan=True,
    ):
        raise ValueError("all compared results must use the same actual values")
    if metric not in result.metrics:
        raise ValueError(f"result {name!r} does not contain metric {metric!r}")
    return float(result.metrics[metric])


def compare_forecasts(results, *, metric="rmse"):
    """Rank comparable OOS or backtest results by an error metric.

    All results must use the same target, target indices, and actual values.
    Lower metric values rank first; non-finite scores rank last.
    """
    items = _comparison_items(results, metric)
    reference = _comparison_reference(items)
    scores = {
        name: _comparable_score(name, result, reference, metric)
        for name, result in items
    }

    return ComparisonResult(
        metric=metric,
        scores=scores,
        target=reference.target,
    )
