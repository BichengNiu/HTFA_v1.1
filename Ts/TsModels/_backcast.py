"""Reverse-time pre-sample estimation for predictive models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from Ts.TsMetrics._evaluation import (
    expected_forecast_shape,
    model_data,
    prediction_arrays,
)
from Ts.TsUtils._validation import validate_alpha, validate_positive_int


def _optional_array(values):
    """Return a copied float array while preserving None."""
    if values is None:
        return None
    return np.array(values, dtype=float, copy=True)


@dataclass
class BackcastResult:
    """Chronological pre-sample reverse-time estimates."""

    mean: np.ndarray
    lower: np.ndarray | None
    upper: np.ndarray | None
    indices: np.ndarray
    model_type: str
    target: str

    def __post_init__(self):
        """Normalise arrays and require one index per backcast period."""
        self.mean = np.array(self.mean, dtype=float, copy=True)
        self.lower = _optional_array(self.lower)
        self.upper = _optional_array(self.upper)
        self.indices = np.array(self.indices, dtype=int, copy=True)
        if self.mean.ndim not in (1, 2):
            raise ValueError("mean must have shape (steps,) or (steps, n_series)")
        if self.indices.shape != (self.mean.shape[0],):
            raise ValueError("indices must contain one entry per backcast period")
        for name, values in (("lower", self.lower), ("upper", self.upper)):
            if values is not None and values.shape != self.mean.shape:
                raise ValueError(
                    f"{name} must have the same shape as mean, got "
                    f"{values.shape} and {self.mean.shape}"
                )


def backcast_model(model, steps, alpha=0.05):
    """Estimate pre-sample values by reverse-time refitting."""
    steps = validate_positive_int("steps", steps)
    alpha = validate_alpha(alpha)
    data = model_data(model)
    model._validate_evaluation("backcast")

    reversed_model = model._clone_for_evaluation(data[::-1], exog=None)
    fitted = reversed_model.fit()
    predict = getattr(fitted, "predict", None)
    if not callable(predict):
        raise NotImplementedError(f"{type(model).__name__} does not provide predict()")
    prediction = predict(
        start=fitted.nobs,
        end=fitted.nobs + steps - 1,
        alpha=alpha,
    )
    expected_shape = expected_forecast_shape(data, steps)
    mean, lower, upper = prediction_arrays(prediction, expected_shape)
    return BackcastResult(
        mean=mean[::-1].copy(),
        lower=None if lower is None else lower[::-1].copy(),
        upper=None if upper is None else upper[::-1].copy(),
        indices=np.arange(-steps, 0, dtype=int),
        model_type=fitted.model_type,
        target=model._backcast_target_name,
    )
