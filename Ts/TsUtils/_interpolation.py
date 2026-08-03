"""Missing-value interpolation for univariate and multivariate time series."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_METHODS = frozenset({"linear", "time", "nearest", "cubic"})
_EDGE_POLICIES = frozenset({"keep", "nearest"})


def _copy_data(data):
    """Return an isolated copy while preserving the public container type."""
    if isinstance(data, (pd.Series, pd.DataFrame)):
        return data.copy(deep=True)
    return np.array(data, dtype=float, copy=True)


@dataclass
class InterpolationResult:
    """Interpolated data plus an explicit missing-value audit trail."""

    data: np.ndarray | pd.Series | pd.DataFrame
    missing_mask: np.ndarray
    filled_mask: np.ndarray
    method: str
    max_gap: int | None
    edge: str

    def __post_init__(self):
        """Copy result state and require masks aligned with the output."""
        self.data = _copy_data(self.data)
        self.missing_mask = np.array(
            self.missing_mask,
            dtype=bool,
            copy=True,
        )
        self.filled_mask = np.array(
            self.filled_mask,
            dtype=bool,
            copy=True,
        )
        self.method, self.max_gap, self.edge = _normalise_options(
            self.method,
            self.max_gap,
            self.edge,
        )
        shape = np.asarray(self.data).shape
        for name, mask in (
            ("missing_mask", self.missing_mask),
            ("filled_mask", self.filled_mask),
        ):
            if mask.shape != shape:
                raise ValueError(
                    f"{name} must have the same shape as data, "
                    f"got {mask.shape} and {shape}"
                )
        if np.any(self.filled_mask & ~self.missing_mask):
            raise ValueError("filled_mask must be a subset of missing_mask")
        values = np.asarray(self.data, dtype=float)
        if np.any(self.filled_mask & np.isnan(values)):
            raise ValueError("filled_mask positions must contain filled values")

    @property
    def n_missing(self):
        """Number of originally missing values."""
        return int(self.missing_mask.sum())

    @property
    def n_filled(self):
        """Number of missing values filled by this operation."""
        return int(self.filled_mask.sum())

    @property
    def n_remaining(self):
        """Number of originally missing values that remain missing."""
        return int(self.remaining_mask.sum())

    @property
    def remaining_mask(self):
        """Originally missing positions that were not filled."""
        return self.missing_mask & ~self.filled_mask

    @property
    def complete(self):
        """Whether every originally missing value was filled."""
        return self.n_remaining == 0

    def summary(self):
        """Return a compact interpolation audit summary."""
        max_gap = "None" if self.max_gap is None else str(self.max_gap)
        lines = [
            "Interpolation Result",
            "=" * 40,
            f"Method          : {self.method}",
            f"Maximum gap     : {max_gap}",
            f"Edge policy     : {self.edge}",
            f"Missing values  : {self.n_missing}",
            f"Filled values   : {self.n_filled}",
            f"Remaining       : {self.n_remaining}",
            f"Complete        : {self.complete}",
        ]
        return "\n".join(lines)


def _normalise_options(method, max_gap, edge):
    """Validate and return normalised interpolation options."""
    if not isinstance(method, str) or method not in _METHODS:
        supported = ", ".join(sorted(_METHODS))
        raise ValueError(f"method must be one of: {supported}")
    if max_gap is not None and (
        isinstance(max_gap, (bool, np.bool_))
        or not isinstance(max_gap, (int, np.integer))
        or max_gap < 1
    ):
        raise ValueError("max_gap must be None or a non-boolean integer >= 1")
    if not isinstance(edge, str) or edge not in _EDGE_POLICIES:
        raise ValueError("edge must be 'keep' or 'nearest'")
    return method, None if max_gap is None else int(max_gap), edge


def _numeric_frame(data):
    """Return a float DataFrame and metadata for restoring input type."""
    if isinstance(data, pd.Series):
        try:
            numeric = pd.to_numeric(data, errors="raise").astype(float)
        except (TypeError, ValueError) as error:
            raise TypeError("data must contain only numeric values") from error
        frame = numeric.to_frame()
        frame.attrs["_series_name"] = data.name
        kind = "series"
    elif isinstance(data, pd.DataFrame):
        try:
            frame = data.apply(pd.to_numeric, errors="raise").astype(float)
        except (TypeError, ValueError) as error:
            raise TypeError("data must contain only numeric values") from error
        kind = "dataframe"
    else:
        array = np.asarray(data)
        if array.ndim not in (1, 2):
            raise ValueError("data must be one- or two-dimensional")
        try:
            numeric = np.asarray(data, dtype=float)
        except (TypeError, ValueError) as error:
            raise TypeError("data must contain only numeric values") from error
        if numeric.ndim == 1:
            frame = pd.DataFrame(numeric)
            kind = "array1d"
        else:
            frame = pd.DataFrame(numeric)
            kind = "array2d"

    if frame.shape[0] == 0:
        raise ValueError("data must contain at least one observation")
    if frame.shape[1] == 0:
        raise ValueError("data must contain at least one series")

    values = frame.to_numpy(dtype=float, copy=True)
    infinite = np.argwhere(np.isinf(values))
    if infinite.size:
        positions = ", ".join(
            f"({int(row)}, {int(column)})" for row, column in infinite
        )
        raise ValueError(f"data contains infinite values at positions: {positions}")
    return frame.copy(deep=True), kind


def _eligible_missing(mask, max_gap):
    """Return missing positions whose consecutive run is eligible to fill."""
    eligible = np.array(mask, dtype=bool, copy=True)
    if max_gap is None:
        return eligible

    for column in range(mask.shape[1]):
        padded = np.concatenate(([False], mask[:, column], [False]))
        changes = np.diff(padded.astype(np.int8))
        starts = np.flatnonzero(changes == 1)
        stops = np.flatnonzero(changes == -1)
        for start, stop in zip(starts, stops, strict=True):
            if stop - start > max_gap:
                eligible[start:stop, column] = False
    return eligible


def _validate_time_index(frame):
    """Require an unambiguous chronological index for time interpolation."""
    if not isinstance(frame.index, (pd.DatetimeIndex, pd.TimedeltaIndex)):
        raise TypeError(
            "method='time' requires a pandas DatetimeIndex or TimedeltaIndex"
        )
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("time index must be unique and increasing")


def _interpolate_frame(frame, method):
    """Delegate supported interior interpolation to pandas."""
    if method == "time":
        _validate_time_index(frame)
    try:
        return frame.interpolate(
            method=method,
            axis=0,
            limit_area="inside",
        )
    except (TypeError, ValueError, NotImplementedError) as error:
        raise ValueError(f"{method} interpolation failed: {error}") from error


def _fill_nearest_edges(output, original, missing, eligible):
    """Fill eligible boundary gaps from the nearest observed value."""
    for column in range(original.shape[1]):
        observed = np.flatnonzero(~missing[:, column])
        if not observed.size:
            continue
        first = int(observed[0])
        last = int(observed[-1])
        leading = np.arange(first)
        trailing = np.arange(last + 1, original.shape[0])
        leading = leading[eligible[leading, column]]
        trailing = trailing[eligible[trailing, column]]
        output[leading, column] = original[first, column]
        output[trailing, column] = original[last, column]


def _restore_data(values, frame, kind):
    """Restore the caller's logical container type and metadata."""
    if kind == "series":
        return pd.Series(
            values[:, 0],
            index=frame.index.copy(),
            name=frame.attrs.get("_series_name"),
        )
    if kind == "dataframe":
        return pd.DataFrame(
            values,
            index=frame.index.copy(),
            columns=frame.columns.copy(),
        )
    if kind == "array1d":
        return values[:, 0].copy()
    return values.copy()


def interpolate_missing(
    data,
    method="linear",
    *,
    max_gap=None,
    edge="keep",
):
    """Interpolate missing observations without mutating the input.

    Parameters
    ----------
    data : array-like, pandas.Series, or pandas.DataFrame
        Numeric observations ordered along rows.
    method : {"linear", "time", "nearest", "cubic"}
        Interpolation method. ``"time"`` requires a unique, increasing
        DatetimeIndex or TimedeltaIndex.
    max_gap : int, optional
        Maximum consecutive missing run eligible for filling. Longer runs are
        retained in full.
    edge : {"keep", "nearest"}
        Boundary policy. ``"keep"`` performs true interpolation only;
        ``"nearest"`` explicitly fills eligible leading and trailing gaps.

    Returns
    -------
    InterpolationResult
        Type-preserving data plus masks and counts describing what changed.
    """
    method, max_gap, edge = _normalise_options(method, max_gap, edge)
    frame, kind = _numeric_frame(data)
    original = frame.to_numpy(dtype=float, copy=True)
    missing = np.isnan(original)
    eligible = _eligible_missing(missing, max_gap)
    candidate = _interpolate_frame(frame, method).to_numpy(
        dtype=float,
        copy=True,
    )

    output = original.copy()
    fillable = eligible & ~np.isnan(candidate)
    output[fillable] = candidate[fillable]
    if edge == "nearest":
        _fill_nearest_edges(output, original, missing, eligible)

    filled = missing & ~np.isnan(output)
    restored = _restore_data(output, frame, kind)
    public_missing = missing[:, 0] if kind in {"series", "array1d"} else missing
    public_filled = filled[:, 0] if kind in {"series", "array1d"} else filled
    return InterpolationResult(
        data=restored,
        missing_mask=public_missing,
        filled_mask=public_filled,
        method=method,
        max_gap=max_gap,
        edge=edge,
    )
