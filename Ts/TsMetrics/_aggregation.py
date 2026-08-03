"""Metric aggregation over evaluation result axes."""

from __future__ import annotations

from ._metrics import compute_metrics


def metrics_by_horizon(actual, predicted):
    """Compute one metric dictionary per forecast horizon."""
    if actual.shape != predicted.shape or predicted.ndim not in (2, 3):
        raise ValueError("backtest actual and predicted must share a 2D or 3D shape")
    return [
        compute_metrics(actual[:, index], predicted[:, index])
        for index in range(predicted.shape[1])
    ]


def oos_metrics_by_series(actual, predicted):
    """Compute one metric dictionary per endogenous series."""
    if actual.shape != predicted.shape:
        raise ValueError("OOS actual and predicted must have the same shape")
    if predicted.ndim == 1:
        return [compute_metrics(actual, predicted)]
    if predicted.ndim == 2:
        return [
            compute_metrics(actual[:, index], predicted[:, index])
            for index in range(predicted.shape[1])
        ]
    raise ValueError(
        f"unsupported evaluation shape for series metrics: {predicted.shape}"
    )


def backtest_metrics_by_series(actual, predicted):
    """Compute rolling-origin metrics for each endogenous series."""
    if actual.shape != predicted.shape:
        raise ValueError("backtest actual and predicted must have the same shape")
    if predicted.ndim == 2:
        return [compute_metrics(actual, predicted)]
    if predicted.ndim == 3:
        return [
            compute_metrics(actual[:, :, index], predicted[:, :, index])
            for index in range(predicted.shape[2])
        ]
    raise ValueError(
        f"unsupported backtest shape for series metrics: {predicted.shape}"
    )
