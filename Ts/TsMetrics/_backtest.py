"""Leakage-free rolling-origin forecast evaluation."""

from __future__ import annotations

import numpy as np

from ._evaluation import (
    evaluation_actual,
    expected_forecast_shape,
    fit_and_forecast,
    model_data,
    training_dates,
    training_exog,
    validate_model_protocol,
)
from Ts.TsUtils._validation import validate_alpha, validate_positive_int
from ._periods import validated_model_dates
from ._results import BacktestResult


def _validate_backtest_args(
    data,
    initial_window,
    horizon,
    step,
    window,
    window_size,
    alpha,
    on_error,
):
    """Validate public arguments and resolve the rolling window size."""
    initial_window = validate_positive_int(
        "initial_window",
        initial_window,
        minimum=10,
    )
    horizon = validate_positive_int("horizon", horizon)
    step = validate_positive_int("step", step)
    if window not in {"expanding", "rolling"}:
        raise ValueError(
            f"window must be either 'expanding' or 'rolling', got {window!r}"
        )
    if on_error not in {"raise", "record"}:
        raise ValueError(
            f"on_error must be either 'raise' or 'record', got {on_error!r}"
        )
    alpha = validate_alpha(alpha)

    if window == "expanding":
        if window_size is not None:
            raise ValueError("window_size is only valid when window='rolling'")
    elif window_size is None:
        window_size = initial_window
    else:
        window_size = validate_positive_int(
            "window_size",
            window_size,
            minimum=10,
        )
        if window_size > initial_window:
            raise ValueError(
                "window_size must be <= initial_window for rolling windows"
            )
    if initial_window + horizon > len(data):
        raise ValueError(
            "initial_window + horizon must not exceed the number of "
            f"observations ({len(data)})"
        )
    return initial_window, horizon, step, window_size, alpha


def backtest(
    model,
    initial_window,
    *,
    horizon=1,
    step=1,
    window="expanding",
    window_size=None,
    alpha=0.05,
    on_error="raise",
):
    """Run expanding- or rolling-window historical forecast evaluation."""
    data = model_data(model)
    target = validate_model_protocol(model, "backtest")
    dates = validated_model_dates(model, data)
    (
        initial_window,
        horizon,
        step,
        window_size,
        alpha,
    ) = _validate_backtest_args(
        data,
        initial_window,
        horizon,
        step,
        window,
        window_size,
        alpha,
        on_error,
    )

    origins = np.arange(
        initial_window,
        len(data) - horizon + 1,
        step,
        dtype=int,
    )
    one_forecast_shape = expected_forecast_shape(data, horizon)
    output_shape = (len(origins), *one_forecast_shape)
    mean = np.full(output_shape, np.nan)
    actual = np.full(output_shape, np.nan)
    lower = np.full(output_shape, np.nan)
    upper = np.full(output_shape, np.nan)
    has_interval = False
    failures = []
    model_type = type(model).__name__

    for row, origin in enumerate(origins):
        train_start = 0 if window == "expanding" else max(0, int(origin) - window_size)
        train_data = data[train_start:origin]
        try:
            predict_kwargs = model._evaluation_predict_kwargs(
                origin,
                origin + horizon,
            )
            forecast_model_type, forecast = fit_and_forecast(
                model,
                train_data,
                training_exog(model, train_start, origin),
                training_dates(dates, train_start, origin),
                predict_kwargs,
                horizon,
                alpha,
                one_forecast_shape,
            )
            forecast_mean, forecast_lower, forecast_upper = forecast
            observed = data[origin : origin + horizon]
            target_values = evaluation_actual(
                model,
                observed,
                train_data,
                one_forecast_shape,
            )

            mean[row] = forecast_mean
            actual[row] = target_values
            if forecast_lower is not None:
                lower[row] = forecast_lower
                upper[row] = forecast_upper
                has_interval = True
            model_type = forecast_model_type
        except Exception as error:
            if on_error == "raise":
                raise
            failures.append(
                {
                    "origin": int(origin),
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )

    return BacktestResult(
        mean=mean,
        actual=actual,
        lower=lower if has_interval else None,
        upper=upper if has_interval else None,
        origins=origins,
        failures=failures,
        model_type=model_type,
        window=window,
        target=target,
    )
