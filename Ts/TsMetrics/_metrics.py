"""Point-forecast performance metrics."""

from __future__ import annotations

import numpy as np


def _paired_values(actual, predicted, nan_policy):
    """Return aligned finite float vectors under the requested NaN policy."""
    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if actual_array.shape != predicted_array.shape:
        raise ValueError(
            "actual and predicted must have the same shape, got "
            f"{actual_array.shape} and {predicted_array.shape}"
        )
    if nan_policy not in {"omit", "raise"}:
        raise ValueError(
            f"nan_policy must be either 'omit' or 'raise', got {nan_policy!r}"
        )

    actual_flat = actual_array.ravel()
    predicted_flat = predicted_array.ravel()
    finite = np.isfinite(actual_flat) & np.isfinite(predicted_flat)
    if nan_policy == "raise" and not np.all(finite):
        raise ValueError("actual and predicted contain non-finite pairs")
    return actual_flat[finite], predicted_flat[finite]


def _mean_or_nan(values):
    """Return a float mean without warning for an empty vector."""
    if values.size == 0:
        return float("nan")
    return float(np.mean(values))


def _errors(actual, predicted):
    """Subtract finite vectors while allowing a mathematically infinite error."""
    with np.errstate(over="ignore", invalid="ignore"):
        return predicted - actual


def _root_mean_square(values):
    """Return RMS using scaling that avoids avoidable square overflow."""
    if values.size == 0:
        return float("nan")
    absolute = np.abs(values)
    scale = float(np.max(absolute))
    if scale == 0.0:
        return 0.0
    if not np.isfinite(scale):
        return float("inf")
    scaled = absolute / scale
    return float(scale * np.sqrt(np.mean(scaled * scaled)))


def _mape_values(actual, predicted):
    """Compute MAPE from already paired finite vectors."""
    nonzero = actual != 0.0
    if not np.any(nonzero):
        return float("nan")
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        relative_errors = np.abs(predicted[nonzero] / actual[nonzero] - 1.0)
    return float(np.mean(relative_errors) * 100.0)


def _smape_values(actual, predicted):
    """Compute sMAPE without overflowing pairwise sums."""
    if actual.size == 0:
        return float("nan")
    scale = np.maximum(np.abs(actual), np.abs(predicted))
    terms = np.zeros_like(scale)
    positive = scale > 0.0
    scaled_actual = actual[positive] / scale[positive]
    scaled_predicted = predicted[positive] / scale[positive]
    terms[positive] = (
        2.0
        * np.abs(scaled_predicted - scaled_actual)
        / (np.abs(scaled_actual) + np.abs(scaled_predicted))
    )
    return float(np.mean(terms) * 100.0)


def _theil_u1_values(actual, predicted):
    """Compute Theil U1 after cancelling a common stable scale."""
    if actual.size == 0:
        return float("nan")
    scale = float(max(np.max(np.abs(actual)), np.max(np.abs(predicted))))
    if scale == 0.0:
        return 0.0
    scaled_actual = actual / scale
    scaled_predicted = predicted / scale
    numerator = _root_mean_square(scaled_predicted - scaled_actual)
    denominator = _root_mean_square(scaled_actual) + _root_mean_square(scaled_predicted)
    return float(numerator / denominator)


def mae(actual, predicted, *, nan_policy="omit"):
    """Return mean absolute error."""
    actual_values, predicted_values = _paired_values(
        actual,
        predicted,
        nan_policy,
    )
    return _mean_or_nan(np.abs(_errors(actual_values, predicted_values)))


def mse(actual, predicted, *, nan_policy="omit"):
    """Return mean squared error."""
    actual_values, predicted_values = _paired_values(
        actual,
        predicted,
        nan_policy,
    )
    with np.errstate(over="ignore"):
        squared_errors = np.square(_errors(actual_values, predicted_values))
    return _mean_or_nan(squared_errors)


def rmse(actual, predicted, *, nan_policy="omit"):
    """Return root mean squared error."""
    actual_values, predicted_values = _paired_values(
        actual,
        predicted,
        nan_policy,
    )
    return _root_mean_square(_errors(actual_values, predicted_values))


def mape(actual, predicted, *, nan_policy="omit"):
    """Return mean absolute percentage error in percentage points.

    Pairs whose actual value is zero are excluded because their percentage
    error is undefined. The result is NaN when no non-zero actual remains.
    """
    actual_values, predicted_values = _paired_values(
        actual,
        predicted,
        nan_policy,
    )
    return _mape_values(actual_values, predicted_values)


def smape(actual, predicted, *, nan_policy="omit"):
    """Return symmetric mean absolute percentage error.

    Terms where both actual and prediction are zero contribute zero.
    """
    actual_values, predicted_values = _paired_values(
        actual,
        predicted,
        nan_policy,
    )
    return _smape_values(actual_values, predicted_values)


def theil_u1(actual, predicted, *, nan_policy="omit"):
    """Return Theil's U1 inequality coefficient.

    U1 is bounded between zero and one for finite real-valued inputs. It is
    zero for a perfect all-zero forecast.
    """
    actual_values, predicted_values = _paired_values(
        actual,
        predicted,
        nan_policy,
    )
    return _theil_u1_values(actual_values, predicted_values)


def compute_metrics(actual, predicted, *, nan_policy="omit"):
    """Compute the canonical point-forecast metric set.

    Returns MAE, MSE, RMSE, MAPE, sMAPE, Theil U1, and the number of finite
    actual/prediction pairs used by the common error metrics.
    """
    actual_values, predicted_values = _paired_values(
        actual,
        predicted,
        nan_policy,
    )
    n_valid = int(actual_values.size)
    if n_valid == 0:
        return {
            "mae": float("nan"),
            "mse": float("nan"),
            "rmse": float("nan"),
            "mape": float("nan"),
            "smape": float("nan"),
            "theil_u1": float("nan"),
            "n": 0,
        }

    errors = _errors(actual_values, predicted_values)
    absolute_errors = np.abs(errors)
    with np.errstate(over="ignore"):
        squared_errors = np.square(errors)

    return {
        "mae": _mean_or_nan(absolute_errors),
        "mse": _mean_or_nan(squared_errors),
        "rmse": _root_mean_square(errors),
        "mape": _mape_values(actual_values, predicted_values),
        "smape": _smape_values(actual_values, predicted_values),
        "theil_u1": _theil_u1_values(actual_values, predicted_values),
        "n": n_valid,
    }
