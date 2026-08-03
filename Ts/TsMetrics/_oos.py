"""Leakage-free validation over explicit estimation and validation periods."""

from __future__ import annotations

import numpy as np

from Ts.TsUtils._validation import validate_alpha

from ._evaluation import (
    evaluation_actual,
    expected_forecast_shape,
    fit_and_forecast,
    model_data,
    training_dates,
    training_exog,
    validate_model_protocol,
)
from ._periods import resolve_evaluation_periods
from ._results import OOSResult


def _validation_slice(values, offset):
    """Return the scored suffix while preserving an absent interval."""
    if values is None:
        return None
    return np.array(values[offset:], dtype=float, copy=True)


def oos(model, estimation_period, validation_period, *, alpha=0.05):
    """Evaluate a model without exposing validation targets to estimation.

    Both public periods use inclusive bounds. Date-aware models require exact
    date labels; position-based models require zero-based integer positions.
    A gap between the periods is allowed and forecast through, but only the
    validation period is scored.
    """
    data = model_data(model)
    target = validate_model_protocol(model, "oos")
    periods = resolve_evaluation_periods(
        model,
        data,
        estimation_period,
        validation_period,
    )
    alpha = validate_alpha(alpha)

    train_data = data[periods.estimation_start : periods.estimation_stop]
    bridge_horizon = periods.validation_stop - periods.estimation_stop
    bridge_shape = expected_forecast_shape(data, bridge_horizon)
    model_type, (bridge_mean, bridge_lower, bridge_upper) = fit_and_forecast(
        model,
        train_data,
        training_exog(
            model,
            periods.estimation_start,
            periods.estimation_stop,
        ),
        training_dates(
            periods.dates,
            periods.estimation_start,
            periods.estimation_stop,
        ),
        model._evaluation_predict_kwargs(
            periods.estimation_stop,
            periods.validation_stop,
        ),
        bridge_horizon,
        alpha,
        bridge_shape,
    )

    validation_offset = periods.validation_start - periods.estimation_stop
    mean = _validation_slice(bridge_mean, validation_offset)
    lower = _validation_slice(bridge_lower, validation_offset)
    upper = _validation_slice(bridge_upper, validation_offset)
    validation_shape = expected_forecast_shape(
        data,
        periods.validation_stop - periods.validation_start,
    )
    if mean.shape != validation_shape:
        raise ValueError(
            f"validation forecast has shape {mean.shape}, expected {validation_shape}"
        )
    actual = evaluation_actual(
        model,
        data[periods.validation_start : periods.validation_stop],
        train_data,
        validation_shape,
    )

    return OOSResult(
        mean=mean,
        actual=actual,
        lower=lower,
        upper=upper,
        estimation_indices=periods.estimation_indices,
        validation_indices=periods.validation_indices,
        estimation_dates=periods.estimation_dates,
        validation_dates=periods.validation_dates,
        model_type=model_type,
        target=target,
    )
