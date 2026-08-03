"""Descriptive summary and correlogram diagnostics for one time series."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..TsPlots import plot_acf, plot_pacf
from ..TsPlots.style import FIGSIZE
from ._validation import validate_alpha, validate_positive_int

_TEMPORAL_INDEXES = (
    pd.DatetimeIndex,
    pd.PeriodIndex,
    pd.TimedeltaIndex,
)
_PANEL_TITLES = (
    "Level ACF",
    "Level PACF",
    "First-difference ACF",
    "First-difference PACF",
)
_SUMMARY_WIDTH = 50


def _as_numeric_series(data, variable=None) -> pd.Series:
    """Return an isolated numeric Series from supported one-series inputs."""
    if isinstance(data, pd.DataFrame):
        if variable is None and data.shape[1] != 1:
            raise ValueError(
                "variable must be specified when DataFrame has multiple columns"
            )
        if variable is None:
            series = data.iloc[:, 0].copy(deep=True)
        else:
            if variable not in data.columns:
                raise ValueError(f"variable {variable!r} is not a DataFrame column")
            selected = data.loc[:, variable]
            if isinstance(selected, pd.DataFrame):
                raise ValueError(
                    f"variable {variable!r} must identify exactly one column"
                )
            series = selected.copy(deep=True)
    elif isinstance(data, pd.Series):
        if variable is not None:
            raise ValueError("variable is only valid for DataFrame input")
        series = data.copy(deep=True)
    else:
        array = np.asarray(data)
        if array.ndim != 1:
            raise ValueError(f"data must be one-dimensional; got shape {array.shape}")
        series = pd.Series(array)

    if series.empty:
        raise ValueError("data must contain at least one observation")
    try:
        series = pd.to_numeric(series, errors="raise").astype(float)
    except (TypeError, ValueError) as error:
        raise TypeError("data must contain only numeric values") from error
    if np.isinf(series.to_numpy(dtype=float)).any():
        raise ValueError("data must not contain infinite values")
    return series


def _format_value(value) -> str:
    """Format one summary value without hiding undefined statistics."""
    if pd.isna(value):
        return "NA"
    return f"{float(value):.6g}"


def _format_index_value(value) -> str:
    """Format a timestamp, period, duration, or positional index."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class TimeSeriesSummary:
    """Summarise one numeric time series and draw level/difference diagnostics."""

    def __init__(self, data, variable=None, *, nlags=None, alpha=0.05):
        self.series = _as_numeric_series(data, variable=variable)
        self.alpha = validate_alpha(alpha)
        self.nlags = (
            None if nlags is None else validate_positive_int("nlags", nlags, minimum=1)
        )
        self.figure_ = None
        self.axes_ = None

    @property
    def nobs(self) -> int:
        """Total number of observations, including missing values."""
        return len(self.series)

    @property
    def n_missing(self) -> int:
        """Number of missing observations."""
        return int(self.series.isna().sum())

    @property
    def missing_ratio(self) -> float:
        """Share of observations that are missing."""
        return self.n_missing / self.nobs

    @property
    def missing_timestamps(self) -> tuple:
        """Missing timestamps, or positional labels when no time index exists."""
        return tuple(self.series.index[self.series.isna()].tolist())

    @property
    def frequency(self) -> str:
        """Return an explicit/inferred sampling frequency or a clear fallback."""
        index = self.series.index
        if isinstance(index, _TEMPORAL_INDEXES):
            frequency = getattr(index, "freqstr", None)
            if frequency is None and len(index) >= 3:
                try:
                    frequency = pd.infer_freq(index)
                except (TypeError, ValueError):
                    frequency = None
            return frequency or "irregular or unknown"
        if isinstance(index, pd.RangeIndex):
            return f"positional (step={index.step})"
        return "unknown"

    def _summary_text(self) -> str:
        """Build the formatted summary from pandas' descriptive statistics."""
        described = self.series.describe()
        temporal = isinstance(self.series.index, _TEMPORAL_INDEXES)
        missing_label = "Missing timestamps" if temporal else "Missing positions"
        missing_values = ", ".join(
            _format_index_value(value) for value in self.missing_timestamps
        )
        if not missing_values:
            missing_values = "None"

        lines = [
            "Time Series Summary",
            "=" * _SUMMARY_WIDTH,
            f"Name               : "
            f"{self.series.name if self.series.name is not None else 'Unnamed'}",
            f"Observations       : {self.nobs}",
            f"Valid observations : {int(described['count'])}",
            f"Frequency          : {self.frequency}",
            f"Start              : {_format_index_value(self.series.index[0])}",
            f"End                : {_format_index_value(self.series.index[-1])}",
            f"Missing values     : {self.n_missing}",
            f"Missing ratio      : {self.missing_ratio:.2%}",
            f"{missing_label:<19}: {missing_values}",
            "-" * _SUMMARY_WIDTH,
            f"Mean               : {_format_value(described['mean'])}",
            f"Standard deviation : {_format_value(described['std'])}",
            f"Minimum            : {_format_value(described['min'])}",
            f"First quartile     : {_format_value(described['25%'])}",
            f"Median             : {_format_value(described['50%'])}",
            f"Third quartile     : {_format_value(described['75%'])}",
            f"Maximum            : {_format_value(described['max'])}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _mark_unavailable(axes, message) -> None:
        """Mark all correlogram panels unavailable without fabricating values."""
        for axis, title in zip(axes.flat, _PANEL_TITLES, strict=True):
            axis.set_title(title)
            axis.text(
                0.5,
                0.5,
                message,
                ha="center",
                va="center",
                transform=axis.transAxes,
                wrap=True,
            )
            axis.set_axis_off()

    def _resolved_nlags(self, difference) -> int | None:
        """Resolve a lag count valid for PACF on level and difference data."""
        maximum = min(len(self.series) // 2 - 1, len(difference) // 2 - 1)
        if maximum < 1:
            return None
        if self.nlags is None:
            return min(40, maximum)
        if self.nlags > maximum:
            raise ValueError(f"nlags must be <= {maximum} for {self.nobs} observations")
        return self.nlags

    @staticmethod
    def _plot_panel(values, axis, plotter, *, nlags, alpha, title) -> None:
        """Draw one existing correlogram or mark a constant series."""
        if values.nunique() <= 1:
            axis.set_title(title)
            axis.text(
                0.5,
                0.5,
                "Not defined for a constant series.",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            axis.set_axis_off()
            return
        plotter(
            values,
            nlags=nlags,
            alpha=alpha,
            title=title,
            ax=axis,
        )

    def plot(self):
        """Draw level and first-difference ACF/PACF panels."""
        figure, axes = plt.subplots(2, 2, figsize=FIGSIZE)
        self.figure_ = figure
        self.axes_ = axes

        if self.n_missing:
            self._mark_unavailable(
                axes,
                "ACF/PACF not computed because the series contains "
                f"{self.n_missing} missing value(s).",
            )
            figure.tight_layout()
            return figure, axes

        difference = self.series.diff().dropna()
        nlags = self._resolved_nlags(difference)
        if nlags is None:
            self._mark_unavailable(
                axes,
                "ACF/PACF require at least five observations.",
            )
            figure.tight_layout()
            return figure, axes

        panel_specs = (
            (self.series, axes[0, 0], plot_acf),
            (self.series, axes[0, 1], plot_pacf),
            (difference, axes[1, 0], plot_acf),
            (difference, axes[1, 1], plot_pacf),
        )
        for (values, axis, plotter), title in zip(
            panel_specs,
            _PANEL_TITLES,
            strict=True,
        ):
            self._plot_panel(
                values,
                axis,
                plotter,
                nlags=nlags,
                alpha=self.alpha,
                title=title,
            )

        figure.tight_layout()
        return figure, axes

    def summary(self, *, plot=True) -> str:
        """Return descriptive statistics and, by default, draw diagnostics."""
        if plot and self.figure_ is None:
            self.plot()
        return self._summary_text()
