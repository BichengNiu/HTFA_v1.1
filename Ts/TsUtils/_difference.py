"""Composable differences for pandas time-series containers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype


def _validate_order(order) -> int:
    """Return a supported difference order after strict integer validation."""
    if isinstance(order, (bool, np.bool_)) or not isinstance(
        order,
        (int, np.integer),
    ):
        raise TypeError("order must be the integer 1 or 2")
    order = int(order)
    if order not in {1, 2}:
        raise ValueError(f"order must be 1 or 2, got {order}")
    return order


def _validate_lag(lag) -> int:
    """Return a strictly positive positional lag."""
    if isinstance(lag, (bool, np.bool_)) or not isinstance(
        lag,
        (int, np.integer),
    ):
        raise TypeError("lag must be a positive integer")
    lag = int(lag)
    if lag < 1:
        raise ValueError(f"lag must be >= 1, got {lag}")
    return lag


def _validate_log(log) -> bool:
    """Return a genuine boolean log-transform flag."""
    if not isinstance(log, (bool, np.bool_)):
        raise TypeError("log must be a boolean")
    return bool(log)


def _as_float_data(data):
    """Validate a pandas time-series container and return a float copy."""
    if not isinstance(data, (pd.Series, pd.DataFrame)):
        raise TypeError("data must be a pandas Series or DataFrame")
    if data.empty:
        raise ValueError("data must contain at least one row and one series")
    if isinstance(data, pd.DataFrame) and not data.columns.is_unique:
        raise ValueError("DataFrame columns must be unique")

    dtypes = [data.dtype] if isinstance(data, pd.Series) else list(data.dtypes)
    if any(
        not is_numeric_dtype(dtype)
        or is_bool_dtype(dtype)
        or is_complex_dtype(dtype)
        for dtype in dtypes
    ):
        raise TypeError("data must contain only real numeric, non-boolean values")

    converted = data.astype(float)
    values = converted.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise ValueError("data contains infinite values")
    return converted


def difference(data, *, order=1, log=False, lag=1):
    """Return an ordinary, log, or explicit-lag difference.

    Parameters
    ----------
    data : pandas.Series or pandas.DataFrame
        Numeric observations. A DataFrame is transformed independently by
        column. Missing values are allowed and propagate through differences.
    order : {1, 2}, default 1
        Number of times to apply the lag operator.
    log : bool, default False
        Apply the natural logarithm before differencing. Every non-missing
        observation must be strictly positive.
    lag : int, default 1
        Positive positional lag. Use the observations per year for a
        year-over-year difference, such as 12 for monthly or 4 for quarterly
        data.

    Returns
    -------
    pandas.Series or pandas.DataFrame
        A new floating-point object with the same index, labels, and shape.

    Notes
    -----
    With lag ``s``, the first-order result is ``(1 - L^s) x_t`` and the
    second-order result is ``(1 - L^s)^2 x_t``. Log differences apply the same
    operator to ``log(x_t)``.
    """
    order = _validate_order(order)
    lag = _validate_lag(lag)
    log = _validate_log(log)
    transformed = _as_float_data(data)

    values = transformed.to_numpy(dtype=float, na_value=np.nan)
    if log and np.any(values[~np.isnan(values)] <= 0.0):
        raise ValueError("log differences require strictly positive values")
    if log:
        transformed = np.log(transformed)

    for _ in range(order):
        transformed = transformed.diff(periods=lag)

    transformed.index = data.index
    if isinstance(data, pd.Series):
        transformed.name = data.name
    else:
        transformed.columns = data.columns
    return transformed
