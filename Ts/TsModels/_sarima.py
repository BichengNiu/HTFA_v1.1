"""SARIMA model estimation via statsmodels SARIMAX.

Provides :class:`SARIMA` and :class:`SARIMAResult`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from Ts.TsUtils._validation import (
    _resolve_missing_rows,
    validate_alpha as _validate_prediction_alpha,
)

from Ts.TsModels._base import (
    BaseModel,
    BaseModelResult,
    PredictResult,
    _resolve_prediction_window,
)
from Ts.TsModels._intervention import (
    EventColumns,
    EventSpec,
    _validate_datetime_index,
    build_event_matrix,
)


@dataclass(frozen=True)
class _SARIMAInputs:
    endog: np.ndarray
    dates: pd.DatetimeIndex | None
    exog: np.ndarray | None
    exog_names: tuple[str, ...]
    future_exog: pd.DataFrame | None
    dropped_positions: tuple[int, ...]


def _numeric_array(values, name):
    try:
        return np.asarray(values, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain numeric values") from error


def _normalise_nonnegative_integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be a non-negative integer")
    value = int(value)
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _normalise_lag_order(value, name):
    """Return an integer order or immutable tuple of active positive lags."""
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return _normalise_nonnegative_integer(value, name)
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a non-negative integer or an iterable of lags")
    try:
        lags = tuple(value)
    except TypeError as error:
        raise TypeError(
            f"{name} must be a non-negative integer or an iterable of lags"
        ) from error
    if not lags:
        return 0

    normalised = []
    for lag in lags:
        if isinstance(lag, (bool, np.bool_)) or not isinstance(lag, (int, np.integer)):
            raise TypeError(f"{name} lags must be positive integers")
        lag = int(lag)
        if lag <= 0:
            raise ValueError(f"{name} lags must be positive integers")
        normalised.append(lag)
    if len(set(normalised)) != len(normalised):
        raise ValueError(f"{name} lags must be unique")
    return tuple(sorted(normalised))


def _normalise_order(order):
    if not isinstance(order, (tuple, list)) or len(order) != 3:
        raise ValueError(f"order must be a tuple of (p, d, q), got {order}")
    p, d, q = order
    return (
        _normalise_lag_order(p, "p"),
        _normalise_nonnegative_integer(d, "d"),
        _normalise_lag_order(q, "q"),
    )


def _normalise_seasonal_order(seasonal_order):
    if not isinstance(seasonal_order, (tuple, list)) or len(seasonal_order) != 4:
        raise ValueError(
            f"seasonal_order must be a tuple of (P, D, Q, s), got {seasonal_order}"
        )
    P, D, Q, s = seasonal_order
    return (
        _normalise_lag_order(P, "P"),
        _normalise_nonnegative_integer(D, "D"),
        _normalise_lag_order(Q, "Q"),
        _normalise_nonnegative_integer(s, "s"),
    )


def _active_lags(order_component):
    if isinstance(order_component, (int, np.integer)):
        return tuple(range(1, int(order_component) + 1))
    return tuple(order_component)


def _maximum_lag(order_component):
    return max(_active_lags(order_component), default=0)


def _display_order(order):
    p, d, q = order
    return (_maximum_lag(p), d, _maximum_lag(q))


def _normalise_exog_names(names, width):
    if names is None:
        raise ValueError("exog_names is required for array exog")
    names = tuple(names)
    if len(names) != width:
        raise ValueError(f"exog_names must contain one name per exog column ({width})")
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("exog_names must contain non-empty strings")
    names = tuple(name.strip() for name in names)
    if len(set(names)) != len(names):
        raise ValueError("exog_names must be unique")
    if any(name.startswith("event__") for name in names):
        raise ValueError("ordinary exog names must not use the event__ namespace")
    return names


def _normalise_data_and_dates(data, dates):
    if isinstance(data, pd.Series):
        if dates is not None:
            raise ValueError("dates must not be provided when data is a pandas Series")
        values = _numeric_array(data.to_numpy(), "data")
        data_dates = (
            _validate_datetime_index(data.index, "data dates")
            if isinstance(data.index, pd.DatetimeIndex)
            else None
        )
    else:
        values = _numeric_array(data, "data")
        data_dates = None if dates is None else _validate_datetime_index(dates, "dates")
    if values.ndim != 1:
        raise ValueError(f"data must be one-dimensional, got shape {values.shape}")
    if data_dates is not None and len(data_dates) != len(values):
        raise ValueError("dates must contain exactly one value per data observation")
    return values.copy(), data_dates


def _normalise_dataframe_exog(exog, dates, exog_names):
    if exog_names is not None:
        raise ValueError("exog_names must not be provided when exog is a DataFrame")
    if dates is None:
        raise ValueError(
            "DataFrame exog requires dated data or an explicit dates argument"
        )
    index = _validate_datetime_index(exog.index, "exog dates")
    if str(index.tz) != str(dates.tz):
        raise ValueError("exog dates timezone must match data dates timezone")
    names = _normalise_exog_names(tuple(exog.columns), exog.shape[1])

    missing_dates = dates.difference(index)
    if len(missing_dates):
        raise ValueError(
            f"exog is missing historical date {missing_dates[0].isoformat()}"
        )
    historical_mask = index <= dates[-1]
    extra_historical = index[historical_mask & ~index.isin(dates)]
    if len(extra_historical):
        raise ValueError(
            f"exog contains extra historical date {extra_historical[0].isoformat()}"
        )

    frame = exog.copy()
    frame.columns = names
    historical = _numeric_array(frame.loc[dates, list(names)], "exog")
    future_frame = frame.loc[index > dates[-1], list(names)].copy()
    if future_frame.empty:
        future_frame = None
    else:
        future_values = _numeric_array(future_frame, "future exog")
        if not np.all(np.isfinite(future_values)):
            raise ValueError("future exog contains non-finite values")
        future_frame = pd.DataFrame(
            future_values,
            index=future_frame.index.copy(),
            columns=names,
        )
    return historical, names, future_frame


def _normalise_array_exog(exog, endog_length, exog_names):
    values = _numeric_array(exog, "exog")
    if values.ndim != 2:
        raise ValueError(f"exog must be two-dimensional, got shape {values.shape}")
    if len(values) != endog_length:
        raise ValueError(
            f"exog has {len(values)} observations; expected {endog_length} observations"
        )
    names = _normalise_exog_names(exog_names, values.shape[1])
    return values.copy(), names


def _normalise_sarima_inputs(
    data,
    *,
    dates=None,
    exog=None,
    exog_names=None,
    missing="raise",
):

    endog, data_dates = _normalise_data_and_dates(data, dates)

    future_exog = None
    if exog is None:
        if exog_names is not None:
            raise ValueError("exog_names requires exog")
        historical_exog = None
        names = ()
    elif isinstance(exog, pd.DataFrame):
        historical_exog, names, future_exog = _normalise_dataframe_exog(
            exog,
            data_dates,
            exog_names,
        )
    else:
        historical_exog, names = _normalise_array_exog(
            exog,
            len(endog),
            exog_names,
        )

    finite = np.isfinite(endog)
    if historical_exog is not None:
        finite &= np.all(np.isfinite(historical_exog), axis=1)
    dropped_positions = _resolve_missing_rows(
        finite,
        missing,
        name="data or historical exog",
    )
    if missing == "drop":
        endog = endog[finite]
        if data_dates is not None:
            data_dates = data_dates[finite].copy()
        if historical_exog is not None:
            historical_exog = historical_exog[finite]

    return _SARIMAInputs(
        endog=endog.copy(),
        dates=data_dates,
        exog=(
            None
            if historical_exog is None
            else np.array(historical_exog, dtype=float, copy=True)
        ),
        dropped_positions=dropped_positions,
        exog_names=names,
        future_exog=future_exog,
    )


def _validate_events(events, dates):
    event_specs = tuple(events or ())
    if any(not isinstance(event, EventSpec) for event in event_specs):
        raise TypeError("events must contain only EventSpec instances")
    if event_specs and dates is None:
        raise ValueError("events require dated data")
    return event_specs


def _validate_design_matrix(frame, trend):
    if frame is None:
        return
    values = frame.to_numpy(dtype=float)
    for index, name in enumerate(frame.columns):
        column = values[:, index]
        if np.all(column == 0.0):
            raise ValueError(f"all-zero design column is not identified: {name}")
        if np.all(column == column[0]) and "c" in trend:
            raise ValueError(
                f"constant exog column {name!r} conflicts with trend={trend!r}"
            )
    rank = np.linalg.matrix_rank(values)
    if rank < values.shape[1]:
        raise ValueError(
            "combined exogenous design matrix is rank deficient: "
            f"rank {rank} for {values.shape[1]} columns"
        )


def _combined_design(inputs, events, trend):
    index = (
        inputs.dates if inputs.dates is not None else pd.RangeIndex(len(inputs.endog))
    )
    frames = []
    if inputs.exog is not None:
        frames.append(
            pd.DataFrame(
                inputs.exog,
                index=index,
                columns=inputs.exog_names,
            )
        )
    event_metadata: dict[str, EventColumns] = {}
    event_frame = None
    if events:
        event_frame, event_metadata = build_event_matrix(
            inputs.dates,
            events,
            reserved_names=inputs.exog_names,
        )
        frames.append(event_frame)
    design = pd.concat(frames, axis=1) if frames else None
    _validate_design_matrix(design, trend)
    return design, event_frame, event_metadata


@dataclass
class ScenarioForecastResult:
    """Forecasts produced from multiple future-exogenous scenarios."""

    scenarios: dict[str, PredictResult]
    default_name: str | None
    dates: pd.DatetimeIndex | None

    def __post_init__(self):
        if not isinstance(self.scenarios, dict) or not self.scenarios:
            raise ValueError("scenarios must be a non-empty dictionary")
        if any(
            not isinstance(name, str) or not name.strip() for name in self.scenarios
        ):
            raise ValueError("scenario names must be non-empty strings")
        lengths = {
            len(np.asarray(prediction.mean)) for prediction in self.scenarios.values()
        }
        if len(lengths) != 1:
            raise ValueError("all scenario predictions must have equal length")
        if self.default_name is not None and self.default_name not in self.scenarios:
            raise ValueError("default_name must identify an existing scenario")
        if self.dates is not None:
            self.dates = _validate_datetime_index(
                self.dates,
                "scenario dates",
            ).copy()
            if len(self.dates) != next(iter(lengths)):
                raise ValueError("scenario dates length must match prediction length")
        self.scenarios = dict(self.scenarios)

    def __getitem__(self, name):
        return self.scenarios[name]

    def summary(self):
        """Return a compact scenario inventory."""
        default = self.default_name or "none"
        names = ", ".join(self.scenarios)
        return (
            f"Forecast scenarios: {names}\n"
            f"Default scenario: {default}\n"
            f"Periods: {len(next(iter(self.scenarios.values())).mean)}"
        )

    def plot(self, title=None):
        """Plot all scenario means on shared axes."""
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 5))
        first = next(iter(self.scenarios.values()))
        x = self.dates if self.dates is not None else np.arange(len(first.mean))
        for name, prediction in self.scenarios.items():
            ax.plot(x, prediction.mean, label=name)
        ax.set_title(title or "Forecast Scenarios")
        ax.legend(frameon=False)
        fig.tight_layout()
        return fig, ax


def _coerce_future_frame(
    values,
    *,
    name,
    expected_dates,
    exog_names,
    array_dates_provided,
):
    if isinstance(values, pd.DataFrame):
        actual_columns = tuple(values.columns)
        if actual_columns != exog_names:
            raise ValueError(
                f"scenario {name!r} columns must be exactly {exog_names}, "
                f"got {actual_columns}"
            )
        index = _validate_datetime_index(
            values.index,
            f"scenario {name!r} dates",
        )
        if len(index) != len(expected_dates) or not index.equals(expected_dates):
            raise ValueError(
                f"scenario {name!r} dates/rows must exactly match "
                "the requested future dates"
            )
        array = _numeric_array(values, f"scenario {name!r}")
    else:
        if not array_dates_provided:
            raise ValueError("array future_exog requires future_dates")
        array = _numeric_array(values, f"scenario {name!r}")
        if array.ndim != 2:
            raise ValueError(f"scenario {name!r} must be two-dimensional")
        if array.shape != (len(expected_dates), len(exog_names)):
            raise ValueError(
                f"scenario {name!r} has shape {array.shape}; expected "
                f"{(len(expected_dates), len(exog_names))}"
            )
    if array.ndim != 2 or array.shape != (
        len(expected_dates),
        len(exog_names),
    ):
        raise ValueError(f"scenario {name!r} rows/columns do not match the forecast")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"scenario {name!r} contains non-finite values")
    return pd.DataFrame(
        np.array(array, dtype=float, copy=True),
        index=expected_dates.copy(),
        columns=exog_names,
    )


def _normalise_future_scenarios(
    future_exog,
    *,
    future_dates,
    expected_dates,
    exog_names,
    default_future_exog,
):
    scenarios = {}
    default_name = None
    if default_future_exog is not None:
        missing = expected_dates.difference(default_future_exog.index)
        if len(missing):
            raise ValueError(
                f"default future exog is missing date {missing[0].isoformat()}"
            )
        scenarios["default"] = _coerce_future_frame(
            default_future_exog.loc[expected_dates],
            name="default",
            expected_dates=expected_dates,
            exog_names=exog_names,
            array_dates_provided=True,
        )
        default_name = "default"

    if future_exog is None:
        if not scenarios:
            missing_date = expected_dates[0].isoformat()
            raise ValueError(f"future exog is required starting at {missing_date}")
        return scenarios, default_name

    if isinstance(future_exog, Mapping):
        if not future_exog:
            raise ValueError("future_exog scenario mapping must not be empty")
        items = tuple(future_exog.items())
    else:
        items = (("custom", future_exog),)

    for name, values in items:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("scenario names must be non-empty strings")
        if name == "default":
            raise ValueError("'default' is a reserved scenario name")
        scenarios[name] = _coerce_future_frame(
            values,
            name=name,
            expected_dates=expected_dates,
            exog_names=exog_names,
            array_dates_provided=future_dates is not None,
        )
    return scenarios, default_name


@dataclass
class SARIMAResult(BaseModelResult):
    """Result container for SARIMA model estimation.

    Inherits all fields from :class:`BaseModelResult` and adds SARIMA-specific
    prediction and forecasting methods.

    Parameters
    ----------
    _order : tuple or None
        SARIMA order (p, d, q).
    _seasonal_order : tuple or None
        Seasonal order (P, D, Q, s).
    _statsmodels_result : object
        Raw statsmodels SARIMAXResultsWrapper, stored for internal
        predict / forecast delegation.
    """

    _order: tuple | None = None
    _seasonal_order: tuple | None = None
    _statsmodels_result: object = None
    _trend: str = "c"
    _dates: pd.DatetimeIndex | None = None
    _ordinary_exog: np.ndarray | None = None
    _ordinary_exog_names: tuple[str, ...] = ()
    _event_specs: tuple[EventSpec, ...] = ()
    _event_metadata: dict[str, EventColumns] | None = None
    _design_columns: tuple[str, ...] = ()
    _design_matrix: np.ndarray | None = None
    _default_future_exog: pd.DataFrame | None = None
    _model_kwargs: dict | None = None

    @property
    def dates(self):
        """Return a copy of the fitted observation dates."""
        return None if self._dates is None else self._dates.copy()

    @property
    def exog_names(self):
        """Return ordinary exogenous-variable names."""
        return tuple(self._ordinary_exog_names)

    @property
    def event_names(self):
        """Return event names in model-column order."""
        return tuple(event.name for event in self._event_specs)

    @property
    def design_columns(self):
        """Return the fitted combined-design column names."""
        return tuple(self._design_columns)

    @property
    def ar_lags(self):
        """Active non-seasonal autoregressive lags."""
        if self._order is None:
            return ()
        return _active_lags(self._order[0])

    @property
    def ma_lags(self):
        """Active non-seasonal moving-average lags."""
        if self._order is None:
            return ()
        return _active_lags(self._order[2])

    @property
    def fixed_params(self):
        """Non-seasonal AR/MA coefficients excluded and fixed at zero."""
        fixed = {}
        if self.ar_lags:
            for lag in range(1, max(self.ar_lags) + 1):
                if lag not in self.ar_lags:
                    fixed[f"ar.L{lag}"] = 0.0
        if self.ma_lags:
            for lag in range(1, max(self.ma_lags) + 1):
                if lag not in self.ma_lags:
                    fixed[f"ma.L{lag}"] = 0.0
        return fixed

    @property
    def is_stationary(self):
        """Whether all roots of the fitted AR polynomial lie outside one."""
        return bool(np.all(np.abs(self.arroots) > 1.0))

    @property
    def is_invertible(self):
        """Whether all roots of the fitted MA polynomial lie outside one."""
        return bool(np.all(np.abs(self.maroots) > 1.0))

    @property
    def stationarity_enforced(self):
        """Whether stationarity was enforced during maximum likelihood."""
        if self._model_kwargs is not None:
            return bool(self._model_kwargs.get("enforce_stationarity", True))
        return bool(
            getattr(
                getattr(self._statsmodels_result, "model", None),
                "enforce_stationarity",
                True,
            )
        )

    @property
    def invertibility_enforced(self):
        """Whether invertibility was enforced during maximum likelihood."""
        if self._model_kwargs is not None:
            return bool(self._model_kwargs.get("enforce_invertibility", True))
        return bool(
            getattr(
                getattr(self._statsmodels_result, "model", None),
                "enforce_invertibility",
                True,
            )
        )

    @staticmethod
    def _format_root_diagnostic(roots, passed, *, absent):
        if len(roots) == 0:
            return f"Not applicable ({absent})"
        minimum = float(np.min(np.abs(roots)))
        conclusion = "Passed" if passed else "Failed"
        return f"{conclusion} (minimum |root| = {minimum:.4f})"

    def summary(self) -> str:
        """Return a formatted parameter summary string.

        Overrides BaseModelResult to add SARIMA-specific details (order,
        seasonal_order), sparse-lag constraints, and AR/MA root conditions.
        """
        base = super().summary()
        lines = base.split("\n")
        header_lines = [lines[0]]
        if self._order:
            header_lines.append(f"Order: SARIMA{_display_order(self._order)}")
        if self._seasonal_order and self._seasonal_order != (0, 0, 0, 0):
            header_lines.append(f"Seasonal Order: {self._seasonal_order}")
        if self.ar_lags:
            header_lines.append(
                "Active AR Lags     : " + ", ".join(str(lag) for lag in self.ar_lags)
            )
        if self.ma_lags:
            header_lines.append(
                "Active MA Lags     : " + ", ".join(str(lag) for lag in self.ma_lags)
            )
        if self.fixed_params:
            header_lines.append("Fixed at Zero      : " + ", ".join(self.fixed_params))
        header_lines.extend(
            [
                "AR Stationarity    : "
                + self._format_root_diagnostic(
                    self.arroots,
                    self.is_stationary,
                    absent="no AR terms",
                ),
                "MA Invertibility   : "
                + self._format_root_diagnostic(
                    self.maroots,
                    self.is_invertible,
                    absent="no MA terms",
                ),
                "Stationarity Enforced  : "
                + ("Yes" if self.stationarity_enforced else "No"),
                "Invertibility Enforced : "
                + ("Yes" if self.invertibility_enforced else "No"),
            ]
        )
        return "\n".join(header_lines + lines[1:])

    def _resolve_prediction_bounds(self, start, end, future_dates):
        date_bounds = [
            value
            for value in (start, end)
            if value is not None and not isinstance(value, (int, np.integer))
        ]
        if not date_bounds:
            return start, end
        if self._dates is None:
            raise TypeError("date prediction bounds require dated model data")

        parsed_bounds = []
        for value in date_bounds:
            try:
                timestamp = pd.Timestamp(value)
            except (TypeError, ValueError) as error:
                raise TypeError(
                    "prediction bounds must be integer positions or dates"
                ) from error
            if str(timestamp.tz) != str(self._dates.tz):
                raise ValueError("prediction date timezone must match model dates")
            parsed_bounds.append(timestamp)

        future_index = None
        future_bound = max(
            (timestamp for timestamp in parsed_bounds if timestamp > self._dates[-1]),
            default=None,
        )
        if future_bound is not None:
            if future_dates is not None:
                future_index = _validate_datetime_index(
                    future_dates,
                    "future_dates",
                )
            else:
                frequency = self._dates.freq or pd.infer_freq(self._dates)
                if frequency is None:
                    raise ValueError(
                        "future_dates is required when date frequency "
                        "cannot be inferred"
                    )
                future_index = pd.date_range(
                    start=self._dates[-1],
                    end=future_bound,
                    freq=frequency,
                )[1:]
        calendar = (
            self._dates if future_index is None else self._dates.append(future_index)
        )

        def position(value, name):
            if value is None or isinstance(value, (int, np.integer)):
                return value
            timestamp = pd.Timestamp(value)
            location = int(calendar.get_indexer([timestamp])[0])
            if location < 0:
                raise ValueError(
                    f"prediction date {timestamp.isoformat()} for {name} "
                    "is absent from the prediction calendar"
                )
            return location

        return position(start, "start"), position(end, "end")

    def _prediction_dates(self, window, future_dates):
        if self._dates is None:
            return None
        parts = []
        if window.in_sample_size:
            parts.append(
                self._dates[window.start : window.start + window.in_sample_size]
            )
        if window.has_forecast:
            parts.append(future_dates[window.forecast_skip :])
        if not parts:
            return None
        result = parts[0]
        for part in parts[1:]:
            result = result.append(part)
        return result

    def _resolve_future_dates(self, steps, future_dates):
        if future_dates is not None:
            dates = _validate_datetime_index(future_dates, "future_dates")
            if len(dates) != steps:
                raise ValueError(
                    f"future_dates has {len(dates)} rows; expected {steps}"
                )
            if self._dates is not None and dates[0] <= self._dates[-1]:
                raise ValueError("future_dates must begin after the sample")
            return dates.copy()
        if self._dates is None:
            return None
        frequency = self._dates.freq or pd.infer_freq(self._dates)
        if frequency is None:
            raise ValueError(
                "future_dates is required when date frequency cannot be inferred"
            )
        return pd.date_range(
            start=self._dates[-1],
            periods=steps + 1,
            freq=frequency,
        )[1:]

    def _future_design(self, ordinary_exog, future_dates):
        frames = []
        if ordinary_exog is not None:
            frames.append(ordinary_exog)
        if self._event_specs:
            if future_dates is None or self._dates is None:
                raise ValueError("future event generation requires future_dates")
            calendar = self._dates.append(future_dates)
            event_frame, _ = build_event_matrix(
                future_dates,
                self._event_specs,
                calendar=calendar,
                reserved_names=self._ordinary_exog_names,
            )
            frames.append(event_frame)
        if not frames:
            return None
        design = pd.concat(frames, axis=1)
        if tuple(design.columns) != self._design_columns:
            raise RuntimeError("future design columns do not match the fitted design")
        return design

    def _predict_one(
        self,
        window,
        *,
        dynamic,
        alpha,
        future_design,
    ):
        start, end = window.start, window.end
        mean = np.full(window.size, np.nan)
        lower = np.full(window.size, np.nan)
        upper = np.full(window.size, np.nan)
        is_oos = np.zeros(window.size, dtype=bool)

        if window.has_forecast:
            n_in = window.in_sample_size
            if n_in > 0:
                pred_in = self._statsmodels_result.get_prediction(
                    start=start, end=self.nobs - 1, dynamic=dynamic
                )
                summary_in = pred_in.summary_frame(alpha=alpha)
                mean[:n_in] = np.asarray(summary_in["mean"])
                lower[:n_in] = np.asarray(summary_in["mean_ci_lower"])
                upper[:n_in] = np.asarray(summary_in["mean_ci_upper"])

            forecast_kwargs = {}
            if future_design is not None:
                forecast_kwargs["exog"] = future_design
            fc = self._statsmodels_result.get_forecast(
                steps=window.forecast_steps,
                **forecast_kwargs,
            )
            fc_frame = fc.summary_frame(alpha=alpha)
            forecast_slice = slice(window.forecast_skip, None)
            mean[n_in:] = np.asarray(fc_frame["mean"])[forecast_slice]
            lower[n_in:] = np.asarray(fc_frame["mean_ci_lower"])[forecast_slice]
            upper[n_in:] = np.asarray(fc_frame["mean_ci_upper"])[forecast_slice]
            is_oos[n_in:] = True

        else:
            pred = self._statsmodels_result.get_prediction(
                start=start, end=end, dynamic=dynamic
            )
            summary = pred.summary_frame(alpha=alpha)
            mean = np.asarray(summary["mean"])
            lower = np.asarray(summary["mean_ci_lower"])
            upper = np.asarray(summary["mean_ci_upper"])

        _full_lower = None
        _full_upper = None
        if self._statsmodels_result is not None and self.fitted_values is not None:
            full_pred = self._statsmodels_result.get_prediction(
                start=0, end=self.nobs - 1
            )
            full_frame = full_pred.summary_frame(alpha=alpha)
            _full_lower = np.asarray(full_frame["mean_ci_lower"])
            _full_upper = np.asarray(full_frame["mean_ci_upper"])

        return PredictResult(
            mean=mean,
            lower=lower,
            upper=upper,
            is_oos=is_oos,
            _full_data=self.data,
            _full_fitted=self.fitted_values,
            _full_lower=_full_lower,
            _full_upper=_full_upper,
            _start=start,
        )

    def predict(
        self,
        start=0,
        end=None,
        dynamic=False,
        alpha=0.05,
        *,
        future_exog=None,
        future_dates=None,
    ):
        """Return predictions under one or more exogenous scenarios."""
        if self._statsmodels_result is None:
            raise RuntimeError("No fitted statsmodels result available")

        start, end = self._resolve_prediction_bounds(
            start,
            end,
            future_dates,
        )
        window = _resolve_prediction_window(self.nobs, start, end)
        alpha = _validate_prediction_alpha(alpha)
        if not window.has_forecast:
            if future_exog is not None or future_dates is not None:
                raise ValueError(
                    "future_exog and future_dates require an out-of-sample range"
                )
            return self._predict_one(
                window,
                dynamic=dynamic,
                alpha=alpha,
                future_design=None,
            )

        resolved_dates = self._resolve_future_dates(
            window.forecast_steps,
            future_dates,
        )
        if self._ordinary_exog_names:
            if resolved_dates is None:
                raise ValueError("future_dates is required for exogenous forecasting")
            ordinary_scenarios, default_name = _normalise_future_scenarios(
                future_exog,
                future_dates=future_dates,
                expected_dates=resolved_dates,
                exog_names=self._ordinary_exog_names,
                default_future_exog=self._default_future_exog,
            )
        else:
            if future_exog is not None:
                raise ValueError(
                    "future_exog is invalid because the model has no "
                    "ordinary exogenous variables"
                )
            ordinary_scenarios = {"default": None}
            default_name = "default"

        predictions = {}
        for name, ordinary_exog in ordinary_scenarios.items():
            predictions[name] = self._predict_one(
                window,
                dynamic=dynamic,
                alpha=alpha,
                future_design=self._future_design(
                    ordinary_exog,
                    resolved_dates,
                ),
            )
        if len(predictions) == 1:
            return next(iter(predictions.values()))
        scenario_dates = self._prediction_dates(window, resolved_dates)
        return ScenarioForecastResult(
            scenarios=predictions,
            default_name=default_name,
            dates=scenario_dates,
        )

    def policy_effect(
        self,
        events,
        *,
        start=0,
        end=None,
        method="simulation",
        alpha=0.05,
        n_draws=2000,
        seed=None,
    ):
        """Estimate conditional effects for selected fitted events."""
        from Ts.TsModels._intervention import estimate_policy_effect

        return estimate_policy_effect(
            self,
            events=events,
            start=start,
            end=end,
            method=method,
            alpha=alpha,
            n_draws=n_draws,
            seed=seed,
        )

    @property
    def arroots(self):
        """Autoregressive (AR) polynomial roots.

        These are the roots of the AR lag polynomial. For stationarity,
        the inverse roots (1 / arroots) must lie inside the unit circle.

        Returns
        -------
        np.ndarray
            AR polynomial roots. Empty array if the model has no AR terms.
        """
        if self._statsmodels_result is None:
            raise RuntimeError("No fitted statsmodels result available")
        return np.asarray(self._statsmodels_result.arroots)

    @property
    def maroots(self):
        """Moving-average (MA) polynomial roots.

        These are the roots of the MA lag polynomial. For invertibility,
        the inverse roots (1 / maroots) must lie inside the unit circle.

        Returns
        -------
        np.ndarray
            MA polynomial roots. Empty array if the model has no MA terms.
        """
        if self._statsmodels_result is None:
            raise RuntimeError("No fitted statsmodels result available")
        return np.asarray(self._statsmodels_result.maroots)

    def plot_roots(self, title=None):
        """Plot inverse AR and MA roots on the complex unit circle.

        Inverse AR roots are shown as blue circles (``"o"``); inverse MA
        roots as orange triangles (``"^"``). Stationarity requires all
        inverse AR roots to lie inside the unit circle. Invertibility
        requires all inverse MA roots to lie inside the unit circle.

        Uses TsPlots global style settings.

        Parameters
        ----------
        title : str, optional
            Chart title. If None, a default title is generated from the
            model order.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        import matplotlib.pyplot as plt

        from Ts.TsPlots.style import (
            AXIS_LABEL_FONTSIZE,
            DEFAULT_PALETTE,
            LEGEND_FONTSIZE,
            TICK_LABELSIZE,
            TITLE_FONTSIZE,
            _ensure_fonts,
            style_axes,
        )

        _ensure_fonts()

        if self._statsmodels_result is None:
            raise RuntimeError("No fitted statsmodels result available")

        ar_roots = np.asarray(self._statsmodels_result.arroots)
        ma_roots = np.asarray(self._statsmodels_result.maroots)

        fig, ax = plt.subplots(figsize=(6, 6))

        theta = np.linspace(0, 2 * np.pi, 400)
        ax.plot(
            np.cos(theta),
            np.sin(theta),
            color=DEFAULT_PALETTE[1],
            linewidth=1.0,
            linestyle="--",
        )

        ax.axhline(0, color=DEFAULT_PALETTE[1], linewidth=0.5, alpha=0.5)
        ax.axvline(0, color=DEFAULT_PALETTE[1], linewidth=0.5, alpha=0.5)

        if len(ar_roots) > 0:
            inv_ar = 1.0 / ar_roots
            ax.scatter(
                inv_ar.real,
                inv_ar.imag,
                color=DEFAULT_PALETTE[0],
                marker="o",
                s=50,
                edgecolors=DEFAULT_PALETTE[7],
                linewidth=0.5,
                zorder=5,
                label="AR roots",
            )

        if len(ma_roots) > 0:
            inv_ma = 1.0 / ma_roots
            ax.scatter(
                inv_ma.real,
                inv_ma.imag,
                color=DEFAULT_PALETTE[4],
                marker="^",
                s=50,
                edgecolors=DEFAULT_PALETTE[7],
                linewidth=0.5,
                zorder=5,
                label="MA roots",
            )

        ax.set_aspect("equal")
        style_axes(ax)

        # Auto-scale limits to keep unit circle and all points visible
        all_re = []
        all_im = []
        for r in list(ar_roots) + list(ma_roots):
            inv = 1.0 / r
            all_re.append(abs(inv.real))
            all_im.append(abs(inv.imag))
        margin = max(1.5, max(all_re + all_im + [0]) * 1.15)
        ax.set_xlim(-margin, margin)
        ax.set_ylim(-margin, margin)

        ax.set_xlabel("Real", fontsize=AXIS_LABEL_FONTSIZE)
        ax.set_ylabel("Imaginary", fontsize=AXIS_LABEL_FONTSIZE)
        ax.tick_params(labelsize=TICK_LABELSIZE)

        if len(ar_roots) > 0 or len(ma_roots) > 0:
            ax.legend(frameon=False, fontsize=LEGEND_FONTSIZE)

        if title is None:
            order_str = f"SARIMA{_display_order(self._order)}"
            if self._seasonal_order and self._seasonal_order != (0, 0, 0, 0):
                order_str += str(self._seasonal_order)
            title = f"{order_str}: Inverse AR and MA Roots"
        ax.set_title(title, fontsize=TITLE_FONTSIZE, fontweight="bold")

        fig.tight_layout(pad=1.5)
        return fig, ax

    def long_run_equilibrium(self):
        """Return the unconditional mean (long-run equilibrium) of the
        estimated SARIMA process.

        For a stationary ARMA/SARMA process with reduced AR polynomial
        :math:`A(B)` and constant :math:`c`:

        .. math::

            \\mu = \\frac{c}{A(1)}

        This reduced-polynomial form handles sparse and multiplicative
        seasonal AR terms without assuming contiguous lag coefficients.

        Returns ``None`` when the concept is not applicable:

        - ``d > 0`` or ``D > 0`` — differencing removes the mean.
        - ``trend`` includes a time component (``"t"``, ``"ct"``, ``"ctt"``)
          — trend-stationary series have no constant equilibrium.
        - AR polynomial is non-stationary (inverse roots on or outside the
          unit circle) or :math:`A(1) \\approx 0`.

        Returns
        -------
        float or None
        """
        if self._statsmodels_result is None:
            raise RuntimeError("No fitted statsmodels result available")

        _p, d, _q = self._order
        _P, D, _Q, _s = self._seasonal_order

        # Differencing removes the unconditional mean
        if (d or 0) + (D or 0) > 0:
            return None

        # Trend-stationary — no constant long-run equilibrium
        if self._trend in ("t", "ct", "ctt"):
            return None

        # Check stationarity of the complete reduced AR polynomial.
        if not self.is_stationary:
            return None

        # trend="n" — zero-mean process
        if self._trend == "n":
            return 0.0

        intercept = self.params.get("intercept", 0.0)
        reduced_ar = np.asarray(
            self._statsmodels_result.polynomial_reduced_ar,
            dtype=float,
        )
        denom = float(np.sum(reduced_ar))
        if abs(denom) < 1e-10:
            return None

        return intercept / denom


class SARIMA(BaseModel):
    """SARIMA model estimation via statsmodels SARIMAX.

    Parameters
    ----------
    data : array-like
        Time series data (1-D).
    order : tuple
        ``(p, d, q)`` non-seasonal order. ``p`` and ``q`` may be
        non-negative integers or iterables containing the exact positive
        lags to estimate. For example, ``([1, 3], 0, 0)`` estimates AR
        lags 1 and 3 while fixing lag 2 at zero.
    seasonal_order : tuple
        ``(P, D, Q, s)`` seasonal order. ``P`` and ``Q`` accept the same
        integer-or-active-lags form. Default ``(0, 0, 0, 0)``.
    trend : str
        Trend specification: ``"n"`` (none), ``"c"`` (constant),
        ``"t"`` (linear), ``"ct"`` (both). Default ``"c"``.
    enforce_stationarity : bool
        Whether to enforce stationarity of the AR polynomial. Default ``True``.
    enforce_invertibility : bool
        Whether to enforce invertibility of the MA polynomial. Default ``True``.
    dates : datetime-like sequence, optional
        Strict sample dates. A Series DatetimeIndex is inferred automatically.
        Array inputs may provide dates explicitly.
    missing : {"raise", "drop"}
        Non-finite input policy. ``"drop"`` records removed zero-based rows
        in :attr:`dropped_positions`. Default ``"raise"``.
    """

    def __init__(
        self,
        data,
        order=(1, 0, 0),
        seasonal_order=(0, 0, 0, 0),
        trend="c",
        enforce_stationarity=True,
        enforce_invertibility=True,
        *,
        dates=None,
        exog=None,
        exog_names=None,
        events=None,
        missing="raise",
    ):
        inputs = _normalise_sarima_inputs(
            data,
            dates=dates,
            exog=exog,
            exog_names=exog_names,
            missing=missing,
        )

        order = _normalise_order(order)
        seasonal_order = _normalise_seasonal_order(seasonal_order)
        if len(inputs.endog) < 10:
            raise ValueError(f"Need at least 10 observations, got {len(inputs.endog)}")
        event_specs = _validate_events(events, inputs.dates)
        design, event_frame, event_metadata = _combined_design(
            inputs,
            event_specs,
            trend,
        )

        self.data = inputs.endog
        self.dates = inputs.dates
        self.exog = inputs.exog
        self.exog_names = inputs.exog_names
        self.future_exog = inputs.future_exog
        self.events = event_specs
        self._event_frame = event_frame
        self._event_metadata = event_metadata
        self._design_frame = design
        self.design_matrix = (
            None if design is None else design.to_numpy(dtype=float, copy=True)
        )
        self.design_columns = () if design is None else tuple(design.columns)
        self.missing = missing
        self.dropped_positions = inputs.dropped_positions
        self.order = tuple(order)
        self.seasonal_order = tuple(seasonal_order)
        self.trend = trend
        self.enforce_stationarity = enforce_stationarity
        self.enforce_invertibility = enforce_invertibility

    def _clone_for_evaluation(self, data, exog=None, *, dates=None):
        """Rebuild all derived design state for an evaluation window."""
        return type(self)(
            data,
            order=self.order,
            seasonal_order=self.seasonal_order,
            trend=self.trend,
            enforce_stationarity=self.enforce_stationarity,
            enforce_invertibility=self.enforce_invertibility,
            dates=dates,
            exog=exog,
            exog_names=self.exog_names if exog is not None else None,
            events=self.events,
            missing="raise",
        )

    def _evaluation_predict_kwargs(self, start, stop):
        """Return future exogenous values and dates for one evaluation."""
        kwargs = {}
        if self.exog is not None:
            expected = stop - start
            future_exog = self.exog[start:stop]
            if len(future_exog) != expected:
                missing_start = max(start, len(self.exog))
                if self.dates is None:
                    missing = f"positions {missing_start} through {stop - 1}"
                else:
                    missing = ", ".join(
                        timestamp.isoformat()
                        for timestamp in self.dates[missing_start:stop]
                    )
                raise ValueError(f"future exog is missing dates: {missing}")
            kwargs["future_exog"] = np.array(
                future_exog,
                dtype=float,
                copy=True,
            )
        if self.dates is not None:
            future_dates = self.dates[start:stop]
            if len(future_dates) != stop - start:
                raise ValueError("future dates do not cover the evaluation window")
            kwargs["future_dates"] = future_dates.copy()
        return kwargs

    def fit(self):
        """Estimate the SARIMA model via maximum likelihood.

        Returns
        -------
        SARIMAResult
        """
        p, d, q = self.order
        P, D, Q, s = self.seasonal_order

        model_dates = self.dates
        if model_dates is not None and (
            model_dates.freq is None and pd.infer_freq(model_dates) is None
        ):
            model_dates = None
        model_exog = self._design_frame
        if model_exog is not None and model_dates is None:
            model_exog = model_exog.reset_index(drop=True)

        model = SARIMAX(
            self.data,
            exog=model_exog,
            dates=model_dates,
            order=(p, d, q),
            seasonal_order=(P, D, Q, s),
            trend=self.trend,
            enforce_stationarity=self.enforce_stationarity,
            enforce_invertibility=self.enforce_invertibility,
        )
        fitted = model.fit(disp=False)

        params = {}
        std_errors = {}
        p_values = {}
        for name, param, bse_val, pval in zip(
            fitted.param_names, fitted.params, fitted.bse, fitted.pvalues, strict=False
        ):
            params[name] = float(param)
            std_errors[name] = float(bse_val)
            p_values[name] = float(pval)

        resid = np.asarray(fitted.resid)
        fitted_vals = np.asarray(fitted.fittedvalues)

        result = SARIMAResult(
            model_type="SARIMA",
            params=params,
            std_errors=std_errors,
            p_values=p_values,
            aic=float(fitted.aic),
            bic=float(fitted.bic),
            log_likelihood=float(fitted.llf),
            residuals=resid,
            fitted_values=fitted_vals,
            nobs=int(fitted.nobs),
            data=self.data.copy(),
            _order=self.order,
            _seasonal_order=self.seasonal_order,
            _statsmodels_result=fitted,
            _trend=self.trend,
            _dates=None if self.dates is None else self.dates.copy(),
            _ordinary_exog=(None if self.exog is None else self.exog.copy()),
            _ordinary_exog_names=self.exog_names,
            _event_specs=self.events,
            _event_metadata=dict(self._event_metadata),
            _design_columns=self.design_columns,
            _design_matrix=(
                None if self.design_matrix is None else self.design_matrix.copy()
            ),
            _default_future_exog=(
                None if self.future_exog is None else self.future_exog.copy()
            ),
            _model_kwargs={
                "order": self.order,
                "seasonal_order": self.seasonal_order,
                "trend": self.trend,
                "enforce_stationarity": self.enforce_stationarity,
                "enforce_invertibility": self.enforce_invertibility,
            },
        )

        self.result_ = result
        return result
