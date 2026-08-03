"""Dated intervention specifications and policy-effect utilities."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset
from pandas.tseries.offsets import (
    BMonthBegin,
    BMonthEnd,
    BQuarterBegin,
    BQuarterEnd,
    BYearBegin,
    BYearEnd,
    MonthBegin,
    MonthEnd,
    QuarterBegin,
    QuarterEnd,
    SemiMonthBegin,
    SemiMonthEnd,
    Tick,
    Week,
    YearBegin,
    YearEnd,
)
from scipy.stats import chi2, norm

DateRule = Literal["exact", "period", "next", "previous"]
EventKind = Literal["pulse", "step"]


@dataclass(frozen=True)
class EventSpec:
    """Immutable definition of one named intervention."""

    name: str
    dates: Sequence[object]
    kind: EventKind
    window: tuple[int, int] | None = None
    reference: int | None = None
    date_rule: DateRule = "period"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("event name must be a non-empty string")
        if self.kind not in {"pulse", "step"}:
            raise ValueError("event kind must be 'pulse' or 'step'")
        if self.date_rule not in {
            "exact",
            "period",
            "next",
            "previous",
        }:
            raise ValueError(
                "date_rule must be 'exact', 'period', 'next', or 'previous'"
            )

        try:
            parsed_dates = tuple(pd.Timestamp(value) for value in self.dates)
        except (TypeError, ValueError) as error:
            raise ValueError("event dates must contain valid dates") from error
        if not parsed_dates:
            raise ValueError("event dates must not be empty")
        if len(set(parsed_dates)) != len(parsed_dates):
            raise ValueError(f"event {self.name.strip()!r} contains duplicate dates")

        if self.kind == "step" and self.window is not None:
            raise ValueError("window is only valid for pulse events")
        if (self.window is None) != (self.reference is None):
            raise ValueError("window and reference must be specified together")
        if self.window is not None:
            if not isinstance(self.window, tuple) or len(self.window) != 2:
                raise ValueError("window must be an ordered pair of integers")
            start, end = self.window
            invalid_bound = (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
            )
            if invalid_bound or start > end:
                raise ValueError("window must be an ordered pair of integers")
            if (
                isinstance(self.reference, bool)
                or not isinstance(self.reference, int)
                or self.reference < start
                or self.reference > end
            ):
                raise ValueError("reference must lie inside window")

        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "dates", parsed_dates)


@dataclass(frozen=True)
class EventColumns:
    """Generated design-column metadata for one event."""

    name: str
    columns: tuple[str, ...]
    relative_periods: tuple[int, ...] | None
    mapped_positions: tuple[int, ...]


_IDENTIFICATION_NOTE = (
    "这是模型条件下的政策效果；只有在外生性、无同期未控冲击、"
    "模型设定正确和反事实稳定等识别条件成立时，才可解释为因果效应。"
)


@dataclass
class PolicyEffectResult:
    """Conditional effect contrast for one or more fitted events."""

    coefficients: pd.DataFrame
    factual_mean: pd.Series
    counterfactual_mean: pd.Series
    effect: pd.Series
    lower: pd.Series
    upper: pd.Series
    cumulative_effect: float
    cumulative_lower: float
    cumulative_upper: float
    pretrend_test: dict | None
    method: str
    identification_note: str

    def __post_init__(self) -> None:
        paths = (
            self.factual_mean,
            self.counterfactual_mean,
            self.effect,
            self.lower,
            self.upper,
        )
        if any(not isinstance(path, pd.Series) for path in paths):
            raise TypeError("policy-effect paths must be pandas Series")
        if any(not path.index.equals(paths[0].index) for path in paths[1:]):
            raise ValueError("policy-effect paths must be aligned")

        self.coefficients = self.coefficients.copy()
        for name in (
            "factual_mean",
            "counterfactual_mean",
            "effect",
            "lower",
            "upper",
        ):
            setattr(self, name, getattr(self, name).copy())

    def summary(self) -> str:
        """Return a self-contained text summary."""
        coefficient_text = (
            "No event coefficients"
            if self.coefficients.empty
            else self.coefficients.to_string(index=False)
        )
        lines = [
            f"Policy effect method: {self.method}",
            "",
            "Event coefficients:",
            coefficient_text,
            "",
            (
                "Cumulative effect: "
                f"{self.cumulative_effect:.6g} "
                f"[{self.cumulative_lower:.6g}, "
                f"{self.cumulative_upper:.6g}]"
            ),
        ]
        if self.pretrend_test is not None:
            lines.extend(
                [
                    "",
                    (
                        "Pretrend Wald test: "
                        f"chi2({self.pretrend_test['df']})="
                        f"{self.pretrend_test['statistic']:.6g}, "
                        f"p={self.pretrend_test['p_value']:.6g}"
                    ),
                ]
            )
        lines.extend(["", f"Identification note: {self.identification_note}"])
        return "\n".join(lines)

    def plot(self, title=None):
        """Plot factual/counterfactual paths and the estimated effect."""
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
        axes[0].plot(
            self.factual_mean.index,
            self.factual_mean,
            label="Factual",
        )
        axes[0].plot(
            self.counterfactual_mean.index,
            self.counterfactual_mean,
            label="Counterfactual",
        )
        axes[0].set_title("Factual and counterfactual paths")
        axes[0].legend(frameon=False)

        axes[1].plot(self.effect.index, self.effect, label="Effect")
        axes[1].fill_between(
            self.effect.index,
            self.lower,
            self.upper,
            alpha=0.2,
            label="Confidence interval",
        )
        axes[1].axhline(0.0, color="black", linewidth=0.8)
        axes[1].set_title("Conditional policy effect")
        axes[1].legend(frameon=False)
        if title is not None:
            fig.suptitle(title)
        fig.tight_layout()
        return fig, axes


_START_OFFSETS = (
    BMonthBegin,
    BQuarterBegin,
    BYearBegin,
    MonthBegin,
    QuarterBegin,
    SemiMonthBegin,
    YearBegin,
)
_END_OFFSETS = (
    BMonthEnd,
    BQuarterEnd,
    BYearEnd,
    MonthEnd,
    QuarterEnd,
    SemiMonthEnd,
    Week,
    YearEnd,
)


def _validate_datetime_index(values, name: str) -> pd.DatetimeIndex:
    try:
        index = pd.DatetimeIndex(values)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be valid datetime values") from error
    if index.empty:
        raise ValueError(f"{name} must not be empty")
    if index.hasnans:
        raise ValueError(f"{name} must not contain missing dates")
    if not index.is_unique:
        raise ValueError(f"{name} must contain unique dates")
    if not index.is_monotonic_increasing:
        raise ValueError(f"{name} must be sorted in increasing order")
    return index


def _same_timezone(left, right) -> bool:
    return str(left) == str(right)


def _period_label(
    event_date: pd.Timestamp,
    calendar: pd.DatetimeIndex,
) -> pd.Timestamp:
    frequency = calendar.freq or pd.infer_freq(calendar)
    if frequency is None:
        raise ValueError("date_rule='period' requires a regular calendar frequency")
    offset = to_offset(frequency)
    normalized = event_date.normalize()
    if isinstance(offset, Tick):
        return event_date.floor(offset)
    if isinstance(offset, _START_OFFSETS):
        return offset.rollback(normalized)
    if isinstance(offset, _END_OFFSETS):
        return offset.rollforward(normalized)
    raise ValueError(f"date_rule='period' does not support frequency {frequency!r}")


def _mapped_position(
    event_date: pd.Timestamp,
    rule: DateRule,
    calendar: pd.DatetimeIndex,
) -> int | None:
    if not _same_timezone(event_date.tz, calendar.tz):
        raise ValueError(
            f"event date {event_date} timezone does not match calendar timezone"
        )

    if rule == "period":
        candidate = _period_label(event_date, calendar)
        position = int(calendar.get_indexer([candidate])[0])
        if position >= 0:
            return position
        if candidate < calendar[0] or candidate > calendar[-1]:
            return None
        raise ValueError(f"period mapping for {event_date} is absent from the calendar")

    if event_date < calendar[0] or event_date > calendar[-1]:
        return None
    if rule == "exact":
        position = int(calendar.get_indexer([event_date])[0])
        if position < 0:
            raise ValueError(
                f"exact event date {event_date.date()} is absent from the calendar"
            )
        return position
    if rule == "next":
        return int(calendar.searchsorted(event_date, side="left"))
    return int(calendar.searchsorted(event_date, side="right") - 1)


def _relative_suffix(relative: int) -> str:
    if relative < 0:
        return f"m{abs(relative)}"
    return f"p{relative}"


def _event_schema(
    event: EventSpec,
) -> tuple[tuple[str, ...], tuple[int, ...] | None]:
    base = f"event__{event.name}"
    if event.window is None:
        return (base,), None
    start, end = event.window
    relative_periods = tuple(
        relative for relative in range(start, end + 1) if relative != event.reference
    )
    columns = tuple(
        f"{base}__{_relative_suffix(relative)}" for relative in relative_periods
    )
    return columns, relative_periods


def build_event_matrix(
    target_dates: pd.DatetimeIndex,
    events: Sequence[EventSpec],
    *,
    calendar: pd.DatetimeIndex | None = None,
    reserved_names: Sequence[str] = (),
) -> tuple[pd.DataFrame, dict[str, EventColumns]]:
    """Build event regressors on target dates using a complete calendar."""
    target_index = _validate_datetime_index(target_dates, "target dates")
    calendar_index = _validate_datetime_index(
        target_index if calendar is None else calendar,
        "calendar",
    )
    target_positions = calendar_index.get_indexer(target_index)
    if np.any(target_positions < 0):
        raise ValueError(
            "target dates must be an exact subset of the complete calendar"
        )

    event_specs = tuple(events)
    event_names = [event.name for event in event_specs]
    if len(set(event_names)) != len(event_names):
        raise ValueError("duplicate event name in events")

    reserved = set(reserved_names)
    all_columns: list[str] = []
    schemas: dict[
        str,
        tuple[tuple[str, ...], tuple[int, ...] | None],
    ] = {}
    for event in event_specs:
        columns, relative_periods = _event_schema(event)
        collisions = reserved.intersection(columns)
        if collisions:
            names = ", ".join(sorted(collisions))
            raise ValueError(f"event column collision: {names}")
        reserved.update(columns)
        all_columns.extend(columns)
        schemas[event.name] = columns, relative_periods

    full = pd.DataFrame(
        0.0,
        index=calendar_index,
        columns=all_columns,
        dtype=float,
    )
    metadata: dict[str, EventColumns] = {}
    for event in event_specs:
        columns, relative_periods = schemas[event.name]
        positions = tuple(
            position
            for event_date in event.dates
            if (
                position := _mapped_position(
                    event_date,
                    event.date_rule,
                    calendar_index,
                )
            )
            is not None
        )
        if event.kind == "step":
            for position in positions:
                full.iloc[position:, full.columns.get_loc(columns[0])] += 1.0
        elif relative_periods is None:
            for position in positions:
                full.iloc[position, full.columns.get_loc(columns[0])] += 1.0
        else:
            for position in positions:
                for column, relative in zip(
                    columns,
                    relative_periods,
                    strict=True,
                ):
                    shifted = position + relative
                    if 0 <= shifted < len(full):
                        full.iloc[
                            shifted,
                            full.columns.get_loc(column),
                        ] += 1.0
        metadata[event.name] = EventColumns(
            name=event.name,
            columns=columns,
            relative_periods=relative_periods,
            mapped_positions=positions,
        )

    matrix = full.iloc[target_positions].copy()
    matrix.index = target_index
    return matrix, metadata


def _selected_event_names(result, events) -> tuple[str, ...]:
    selected = (events,) if isinstance(events, str) else tuple(events)
    if not selected:
        raise ValueError("events must not be empty")
    if any(not isinstance(name, str) for name in selected):
        raise TypeError("events must contain event names")
    if len(set(selected)) != len(selected):
        raise ValueError("events contains duplicate event names")

    known = {event.name for event in result._event_specs}
    unknown = [name for name in selected if name not in known]
    if unknown:
        raise ValueError(f"unknown event: {unknown[0]}")
    return selected


def _event_parameter_table(
    result,
    selected: tuple[str, ...],
    *,
    alpha: float,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    z_critical = float(norm.ppf(1.0 - alpha / 2.0))
    rows = []
    columns = []
    for event in result._event_specs:
        if event.name not in selected:
            continue
        metadata = result._event_metadata[event.name]
        columns.extend(metadata.columns)
        if metadata.relative_periods is None:
            table_entries = ((metadata.columns[0], None, False),)
        else:
            column_by_period = dict(
                zip(
                    metadata.relative_periods,
                    metadata.columns,
                    strict=True,
                )
            )
            table_entries = tuple(
                (
                    (f"event__{event.name}__{_relative_suffix(relative_period)}"),
                    relative_period,
                    relative_period == event.reference,
                )
                for relative_period in range(
                    event.window[0],
                    event.window[1] + 1,
                )
            )
        for column, relative_period, fixed in table_entries:
            if fixed:
                rows.append(
                    {
                        "event": event.name,
                        "column": column,
                        "relative_period": relative_period,
                        "coef": 0.0,
                        "se": np.nan,
                        "z": np.nan,
                        "p": np.nan,
                        "lower": 0.0,
                        "upper": 0.0,
                        "fixed": True,
                    }
                )
                continue
            if metadata.relative_periods is not None:
                column = column_by_period[relative_period]
            estimate = result.params[column]
            standard_error = result.std_errors[column]
            rows.append(
                {
                    "event": event.name,
                    "column": column,
                    "relative_period": relative_period,
                    "coef": estimate,
                    "se": standard_error,
                    "z": estimate / standard_error,
                    "p": result.p_values[column],
                    "lower": estimate - z_critical * standard_error,
                    "upper": estimate + z_critical * standard_error,
                    "fixed": False,
                }
            )
    return pd.DataFrame(rows), tuple(columns)


def _validate_inference_controls(method, n_draws, seed):
    if method not in {"delta", "simulation", "bootstrap"}:
        raise ValueError("method must be 'delta', 'simulation', or 'bootstrap'")
    if (
        isinstance(n_draws, (bool, np.bool_))
        or not isinstance(n_draws, (int, np.integer))
        or n_draws <= 0
    ):
        raise ValueError("n_draws must be a positive integer")
    if seed is not None and (
        isinstance(seed, (bool, np.bool_))
        or not isinstance(seed, (int, np.integer))
        or seed < 0
    ):
        raise ValueError("seed must be a non-negative integer or None")
    return int(n_draws), None if seed is None else int(seed)


def _contrast_standard_errors(
    contrast: np.ndarray,
    covariance: np.ndarray,
) -> np.ndarray:
    variances = np.einsum(
        "ij,jk,ik->i",
        contrast,
        covariance,
        contrast,
    )
    return np.sqrt(np.clip(variances, 0.0, None))


def _delta_intervals(
    contrast: np.ndarray,
    beta: np.ndarray,
    covariance: np.ndarray,
    *,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    effects = contrast @ beta
    standard_errors = _contrast_standard_errors(contrast, covariance)
    z_critical = float(norm.ppf(1.0 - alpha / 2.0))
    cumulative_contrast = contrast.sum(axis=0)
    cumulative_effect = float(cumulative_contrast @ beta)
    cumulative_standard_error = _contrast_standard_errors(
        cumulative_contrast[None, :],
        covariance,
    )[0]
    return (
        effects - z_critical * standard_errors,
        effects + z_critical * standard_errors,
        cumulative_effect - z_critical * cumulative_standard_error,
        cumulative_effect + z_critical * cumulative_standard_error,
    )


def _simulation_intervals(
    contrast: np.ndarray,
    beta: np.ndarray,
    covariance: np.ndarray,
    *,
    alpha: float,
    n_draws: int,
    seed: int | None,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    rng = np.random.default_rng(seed)
    covariance = (covariance + covariance.T) / 2.0
    draws = rng.multivariate_normal(
        beta,
        covariance,
        size=n_draws,
        check_valid="raise",
    )
    return _empirical_intervals(draws @ contrast.T, alpha)


def _empirical_intervals(
    paths: np.ndarray,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    path_array = np.asarray(paths, dtype=float)
    cumulative = path_array.sum(axis=1)
    quantiles = (alpha / 2.0, 1.0 - alpha / 2.0)
    lower, upper = np.quantile(path_array, quantiles, axis=0)
    cumulative_lower, cumulative_upper = np.quantile(
        cumulative,
        quantiles,
    )
    return (
        lower,
        upper,
        float(cumulative_lower),
        float(cumulative_upper),
    )


class _BootstrapError(RuntimeError):
    """Bootstrap threshold failure with per-attempt diagnostics."""

    def __init__(self, message, failures):
        super().__init__(message)
        self.failures = tuple(failures)


def _bootstrap_refit(result, rng):
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    fitted = result._statsmodels_result
    design = pd.DataFrame(
        result._design_matrix,
        columns=result._design_columns,
    )
    simulated = fitted.model.simulate(
        fitted.params,
        nsimulations=result.nobs,
        exog=design,
        random_state=rng,
    )
    refitted = SARIMAX(
        np.asarray(simulated, dtype=float).reshape(-1),
        exog=design,
        **result._model_kwargs,
    ).fit(disp=False)
    if not refitted.mle_retvals.get("converged", False):
        raise RuntimeError("bootstrap refit did not converge")
    return (
        tuple(refitted.param_names),
        np.asarray(refitted.params, dtype=float),
    )


def _bootstrap_intervals(
    result,
    contrast: np.ndarray,
    selected_columns: tuple[str, ...],
    *,
    alpha: float,
    n_draws: int,
    seed: int | None,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    paths = []
    failures = []
    child_seeds = np.random.SeedSequence(seed).spawn(n_draws)
    for attempt, child_seed in enumerate(child_seeds, start=1):
        try:
            parameter_names, parameters = _bootstrap_refit(
                result,
                np.random.default_rng(child_seed),
            )
            positions = [parameter_names.index(column) for column in selected_columns]
            paths.append(contrast @ parameters[positions])
        except Exception as error:
            failures.append(
                {
                    "attempt": attempt,
                    "type": type(error).__name__,
                    "message": str(error),
                }
            )

    success_count = len(paths)
    if success_count / n_draws < 0.8:
        diagnostic = " | ".join(
            f"{failure['type']}: {failure['message']}" for failure in failures[:5]
        )
        message = (
            f"bootstrap produced {success_count}/{n_draws} successful "
            f"refits, below the required 80%; failures: {diagnostic}"
        )
        raise _BootstrapError(message, failures)

    return _empirical_intervals(np.asarray(paths), alpha)


def _selected_relative_periods(
    result,
    selected: tuple[str, ...],
) -> tuple[int | None, ...]:
    periods = []
    for event in result._event_specs:
        if event.name not in selected:
            continue
        metadata = result._event_metadata[event.name]
        periods.extend(metadata.relative_periods or (None,) * len(metadata.columns))
    return tuple(periods)


def _pretrend_wald_test(
    beta: np.ndarray,
    covariance: np.ndarray,
    columns: tuple[str, ...],
    relative_periods: tuple[int | None, ...],
) -> dict | None:
    lead_positions = [
        position
        for position, relative_period in enumerate(relative_periods)
        if relative_period is not None and relative_period < 0
    ]
    if not lead_positions:
        return None
    lead_beta = beta[lead_positions]
    lead_covariance = covariance[np.ix_(lead_positions, lead_positions)]
    statistic = float(lead_beta @ np.linalg.pinv(lead_covariance) @ lead_beta)
    degrees_of_freedom = len(lead_positions)
    return {
        "statistic": statistic,
        "df": degrees_of_freedom,
        "p_value": float(chi2.sf(statistic, degrees_of_freedom)),
        "columns": tuple(columns[position] for position in lead_positions),
    }


def estimate_policy_effect(
    result,
    *,
    events,
    start=0,
    end=None,
    method="simulation",
    alpha=0.05,
    n_draws=2000,
    seed=None,
) -> PolicyEffectResult:
    """Estimate a conditional fitted-event contrast."""
    from Ts.TsUtils._validation import validate_alpha as _validate_prediction_alpha

    from Ts.TsModels._base import (
        _resolve_prediction_window,
    )

    n_draws, seed = _validate_inference_controls(method, n_draws, seed)
    alpha = _validate_prediction_alpha(alpha)
    selected = _selected_event_names(result, events)
    start_position, end_position = result._resolve_prediction_bounds(
        start,
        end,
        None,
    )
    window = _resolve_prediction_window(
        result.nobs,
        start_position,
        end_position,
    )
    future_dates = (
        result._resolve_future_dates(window.forecast_steps, None)
        if window.has_forecast
        else None
    )
    target_dates = result._prediction_dates(window, future_dates)
    if target_dates is None:
        raise TypeError("policy effects require dated model data")

    prediction = result.predict(
        start=start_position,
        end=end_position,
        alpha=alpha,
    )
    if not hasattr(prediction, "mean"):
        raise RuntimeError("policy effects require a single forecast scenario")

    calendar = (
        result._dates if future_dates is None else result._dates.append(future_dates)
    )
    event_frame, _ = build_event_matrix(
        target_dates,
        result._event_specs,
        calendar=calendar,
        reserved_names=result._ordinary_exog_names,
    )
    coefficients, selected_columns = _event_parameter_table(
        result,
        selected,
        alpha=alpha,
    )
    parameter_names = tuple(result._statsmodels_result.param_names)
    parameter_positions = [parameter_names.index(column) for column in selected_columns]
    selected_parameters = np.asarray(
        result._statsmodels_result.params,
        dtype=float,
    )[parameter_positions]
    contrast = event_frame.loc[:, selected_columns].to_numpy(dtype=float)
    effect_values = contrast @ selected_parameters

    full_covariance = np.asarray(
        result._statsmodels_result.cov_params(),
        dtype=float,
    )
    covariance = full_covariance[
        np.ix_(
            parameter_positions,
            parameter_positions,
        )
    ]
    if method == "delta":
        intervals = _delta_intervals(
            contrast,
            selected_parameters,
            covariance,
            alpha=alpha,
        )
    elif method == "simulation":
        intervals = _simulation_intervals(
            contrast,
            selected_parameters,
            covariance,
            alpha=alpha,
            n_draws=n_draws,
            seed=seed,
        )
    else:
        intervals = _bootstrap_intervals(
            result,
            contrast,
            selected_columns,
            alpha=alpha,
            n_draws=n_draws,
            seed=seed,
        )
    lower, upper, cumulative_lower, cumulative_upper = intervals
    relative_periods = _selected_relative_periods(result, selected)
    pretrend_test = _pretrend_wald_test(
        selected_parameters,
        covariance,
        selected_columns,
        relative_periods,
    )
    factual_values = np.asarray(prediction.mean, dtype=float)
    factual = pd.Series(
        factual_values,
        index=target_dates,
        name="factual_mean",
    )
    effect = pd.Series(
        effect_values,
        index=target_dates,
        name="effect",
    )
    cumulative_effect = float(effect_values.sum())
    return PolicyEffectResult(
        coefficients=coefficients,
        factual_mean=factual,
        counterfactual_mean=(factual - effect).rename("counterfactual_mean"),
        effect=effect,
        lower=pd.Series(
            lower,
            index=target_dates,
            name="lower",
        ),
        upper=pd.Series(
            upper,
            index=target_dates,
            name="upper",
        ),
        cumulative_effect=cumulative_effect,
        cumulative_lower=cumulative_lower,
        cumulative_upper=cumulative_upper,
        pretrend_test=pretrend_test,
        method=method,
        identification_note=_IDENTIFICATION_NOTE,
    )
