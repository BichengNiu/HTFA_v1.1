"""Shared private validation helpers for TsUtils."""

from __future__ import annotations

import numpy as np


def validate_positive_int(name, value, minimum=1):
    """Return an integer argument after rejecting booleans and small values."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value,
        (int, np.integer),
    ):
        raise TypeError(f"{name} must be an integer >= {minimum}")
    value = int(value)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def validate_alpha(alpha):
    """Return a finite significance level strictly between zero and one."""
    try:
        alpha = float(alpha)
    except (TypeError, ValueError) as error:
        raise ValueError("alpha must be between 0 and 1") from error
    if not np.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be between 0 and 1, got {alpha}")
    return alpha


def _resolve_missing_rows(finite_rows, missing, *, name="data"):
    """Validate a missing-value policy and return dropped row positions."""
    if missing not in {"raise", "drop"}:
        raise ValueError("missing must be 'raise' or 'drop'")

    finite_rows = np.asarray(finite_rows, dtype=bool)
    if finite_rows.ndim != 1:
        raise ValueError("finite_rows must be one-dimensional")

    dropped_positions = tuple(
        int(position) for position in np.flatnonzero(~finite_rows)
    )
    if dropped_positions and missing == "raise":
        positions = ", ".join(str(position) for position in dropped_positions)
        raise ValueError(
            f"{name} contains non-finite values at row positions: {positions}"
        )
    return dropped_positions
