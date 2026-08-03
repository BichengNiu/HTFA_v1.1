"""Resolution of explicit estimation and validation periods."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EvaluationPeriods:
    """Resolved half-open estimation and validation positions."""

    estimation_start: int
    estimation_stop: int
    validation_start: int
    validation_stop: int
    dates: pd.DatetimeIndex | None

    @property
    def estimation_indices(self):
        return np.arange(self.estimation_start, self.estimation_stop, dtype=int)

    @property
    def validation_indices(self):
        return np.arange(self.validation_start, self.validation_stop, dtype=int)

    @property
    def estimation_dates(self):
        if self.dates is None:
            return None
        return self.dates[self.estimation_start : self.estimation_stop].copy()

    @property
    def validation_dates(self):
        if self.dates is None:
            return None
        return self.dates[self.validation_start : self.validation_stop].copy()


def validated_model_dates(model, data):
    """Return a strict model calendar or None for position-based data."""
    values = getattr(model, "dates", None)
    if values is None:
        return None
    try:
        dates = pd.DatetimeIndex(values)
    except (TypeError, ValueError) as error:
        raise TypeError("model.dates must be datetime-like") from error
    if len(dates) != len(data):
        raise ValueError("model.dates must contain one date per observation")
    if dates.hasnans:
        raise ValueError("model.dates must not contain missing dates")
    if not dates.is_unique:
        raise ValueError("model.dates must be unique")
    if not dates.is_monotonic_increasing:
        raise ValueError("model.dates must be strictly increasing")
    return dates.copy()


def _period_pair(name, period):
    if not isinstance(period, (tuple, list)) or len(period) != 2:
        raise TypeError(f"{name} must be a (start, end) pair")
    return period[0], period[1]


def _position_bound(name, bound, nobs):
    if isinstance(bound, (bool, np.bool_)) or not isinstance(
        bound,
        (int, np.integer),
    ):
        raise TypeError(
            f"{name} must be an integer position because the model has no dates"
        )
    position = int(bound)
    if position < 0 or position >= nobs:
        raise ValueError(
            f"{name}={position} is outside the observed positions 0..{nobs - 1}"
        )
    return position


def _date_bound(name, bound, dates):
    try:
        timestamp = pd.Timestamp(bound)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be datetime-like") from error
    if str(timestamp.tz) != str(dates.tz):
        raise ValueError(f"{name} timezone must match model.dates")
    position = int(dates.get_indexer([timestamp])[0])
    if position < 0:
        raise ValueError(
            f"{name}={timestamp.isoformat()} does not exist in model.dates"
        )
    return position


def _resolve_period(name, period, data, dates):
    start_bound, end_bound = _period_pair(name, period)
    if dates is None:
        start = _position_bound(f"{name} start", start_bound, len(data))
        end = _position_bound(f"{name} end", end_bound, len(data))
    else:
        start = _date_bound(f"{name} start", start_bound, dates)
        end = _date_bound(f"{name} end", end_bound, dates)
    if start > end:
        raise ValueError(f"{name} start must not be later than its end")
    return start, end + 1


def resolve_evaluation_periods(
    model,
    data,
    estimation_period,
    validation_period,
):
    """Validate and resolve inclusive public period bounds."""
    dates = validated_model_dates(model, data)
    estimation_start, estimation_stop = _resolve_period(
        "estimation_period",
        estimation_period,
        data,
        dates,
    )
    validation_start, validation_stop = _resolve_period(
        "validation_period",
        validation_period,
        data,
        dates,
    )
    if estimation_stop - estimation_start < 10:
        raise ValueError("estimation_period must contain at least 10 observations")
    if validation_start < estimation_stop:
        raise ValueError(
            "validation_period must start strictly later than estimation_period ends"
        )
    return EvaluationPeriods(
        estimation_start=estimation_start,
        estimation_stop=estimation_stop,
        validation_start=validation_start,
        validation_stop=validation_stop,
        dates=dates,
    )
