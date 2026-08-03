"""Base classes for all time series models in TsModel.

Provides:

- :class:`BaseModelResult` 鈥?common result container (dataclass).
- :class:`BaseModel` 鈥?abstract base class enforcing the ``fit()`` / ``summary()``
  / ``result_`` contract.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd


# Shared constants used by _garch.py and _auto.py
_VOL_TYPES = frozenset({"GARCH", "EGARCH"})
_GARCH_M_FORMS = frozenset({"vol", "var", "log"})


def _normalise_model_dates(data, dates, expected_length):
    """Return a strict copied DatetimeIndex for a public model input."""
    values = dates
    if values is None:
        index = getattr(data, "index", None)
        if isinstance(index, pd.DatetimeIndex):
            values = index
    if values is None:
        return None
    try:
        index = pd.DatetimeIndex(values)
    except (TypeError, ValueError) as error:
        raise TypeError("dates must be datetime-like") from error
    if len(index) != expected_length:
        raise ValueError(
            f"dates must contain {expected_length} entries, got {len(index)}"
        )
    if index.hasnans:
        raise ValueError("dates must not contain missing values")
    if not index.is_unique:
        raise ValueError("dates must be unique")
    if not index.is_monotonic_increasing:
        raise ValueError("dates must be strictly increasing")
    return index.copy()


@dataclass(frozen=True)
class _PredictionWindow:
    """Resolved positions for a unified prediction request."""

    start: int
    end: int
    size: int
    in_sample_size: int
    forecast_steps: int
    forecast_skip: int

    @property
    def has_forecast(self):
        """Return whether the request reaches beyond the fitted sample."""
        return self.forecast_steps > 0


def _resolve_prediction_window(nobs, start, end):
    """Validate a prediction range and resolve sample/forecast slices."""
    for name, value in (("start", start), ("end", end)):
        if value is None and name == "end":
            continue
        if isinstance(value, (bool, np.bool_)) or not isinstance(
            value,
            (int, np.integer),
        ):
            raise TypeError(f"{name} must be a non-negative integer")

    start = int(start)
    end = nobs - 1 if end is None else int(end)
    if start < 0 or end < 0:
        raise ValueError("start and end must be non-negative")
    if start > end:
        raise ValueError(f"start ({start}) must be <= end ({end})")

    in_sample_end = min(end, nobs - 1)
    in_sample_size = max(0, in_sample_end - start + 1)
    return _PredictionWindow(
        start=start,
        end=end,
        size=end - start + 1,
        in_sample_size=in_sample_size,
        forecast_steps=max(0, end - nobs + 1),
        forecast_skip=max(0, start - nobs),
    )


@dataclass
class PredictResult:
    """Container for unified prediction output.

    Returned by :meth:`BaseModelResult.predict` across all model types.

    Parameters
    ----------
    mean : np.ndarray
        Predicted values, shape ``(n_periods,)`` or ``(n_periods, k)`` for VAR.
    lower : np.ndarray or None
        Lower bound of confidence interval, same shape as *mean*.
    upper : np.ndarray or None
        Upper bound of confidence interval, same shape as *mean*.
    is_oos : np.ndarray
        Boolean mask marking periods beyond the fitted sample.
    """

    mean: np.ndarray
    lower: np.ndarray | None
    upper: np.ndarray | None
    is_oos: np.ndarray
    _full_data: np.ndarray | None = None
    _full_fitted: np.ndarray | None = None
    _full_lower: np.ndarray | None = None
    _full_upper: np.ndarray | None = None
    _start: int | None = None

    def plot(self, ci=False, title=None, xlim=None):
        """Plot prediction results: actual, fitted, forecast, and CI.

        Parameters
        ----------
        ci : bool
            Whether to draw confidence interval bands (default ``False``).
        title : str, optional
            Chart title. Auto-generated when ``None``.
        xlim : tuple of (float, float), optional
            Set x-axis limits, e.g. ``(9800, 10020)`` to zoom in on a
            specific time window.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.ticker import MaxNLocator

        from Ts.TsPlots.style import (
            AXIS_LABEL_FONTSIZE,
            DEFAULT_PALETTE,
            TITLE_FONTSIZE,
            _ensure_fonts,
            style_axes,
        )

        _ensure_fonts()
        fig, ax = plt.subplots(figsize=(10, 5.5))

        has_any = False

        # Layer 1: full historical data
        if self._full_data is not None:
            ax.plot(
                np.arange(len(self._full_data)),
                self._full_data,
                color=DEFAULT_PALETTE[0],
                linestyle="-",
                linewidth=1.5,
                label="Actual",
            )
            has_any = True

        # Layer 2: full in-sample fitted values (+ CI for fitted)
        if self._full_fitted is not None:
            fitted_x = np.arange(len(self._full_fitted))
            ax.plot(
                fitted_x,
                self._full_fitted,
                color=DEFAULT_PALETTE[3],
                linestyle="--",
                linewidth=1.5,
                label="Fitted",
            )
            has_any = True

            if ci and self._full_lower is not None and self._full_upper is not None:
                ax.fill_between(
                    fitted_x,
                    self._full_lower,
                    self._full_upper,
                    color=DEFAULT_PALETTE[3],
                    alpha=0.10,
                    linewidth=0,
                    label="Fitted 95% CI",
                )

        # Layer 3: forecast (OOS portion only)
        oos_mask = np.asarray(self.is_oos, dtype=bool)
        if np.any(oos_mask) and self._start is not None:
            oos_indices = np.where(oos_mask)[0]
            first_oos = oos_indices[0]
            mean_arr = np.asarray(self.mean)

            fc_x = np.arange(self._start, self._start + len(mean_arr))[oos_mask]
            fc_mean = mean_arr[oos_mask]
            forecast_start = self._start + first_oos
            anchor_x = forecast_start - 1

            # Bridge: connect the period immediately before the forecast to
            # its first point.  This makes the forecast line continuous even
            # when prediction begins in the middle of the full sample.
            if first_oos > 0:
                bridge_x = np.concatenate([[anchor_x], fc_x])
                bridge_y = np.concatenate(
                    [
                        [mean_arr[first_oos - 1]],
                        fc_mean,
                    ]
                )
            elif self._full_data is not None and 0 <= anchor_x < len(self._full_data):
                bridge_x = np.concatenate([[anchor_x], fc_x])
                bridge_y = np.concatenate([[self._full_data[anchor_x]], fc_mean])
            else:
                bridge_x, bridge_y = fc_x, fc_mean

            ax.plot(
                bridge_x,
                bridge_y,
                color=DEFAULT_PALETTE[4],
                linestyle="-",
                linewidth=1.5,
                label="Forecast",
            )
            has_any = True

            # Layer 4: forecast confidence interval
            if ci and self.lower is not None and self.upper is not None:
                fc_lower = np.asarray(self.lower)[oos_mask]
                fc_upper = np.asarray(self.upper)[oos_mask]
                ci_x = fc_x
                ci_lower = fc_lower
                ci_upper = fc_upper

                # Anchor the forecast band to the preceding fitted interval.
                # Without this point, the two confidence bands visually break
                # at the in-sample / forecast boundary.
                has_fitted_anchor = (
                    self._full_lower is not None
                    and self._full_upper is not None
                    and 0 <= anchor_x < len(self._full_lower)
                    and anchor_x < len(self._full_upper)
                )
                if has_fitted_anchor:
                    ci_x = np.concatenate([[anchor_x], fc_x])
                    ci_lower = np.concatenate([[self._full_lower[anchor_x]], fc_lower])
                    ci_upper = np.concatenate([[self._full_upper[anchor_x]], fc_upper])
                elif first_oos > 0:
                    lower_arr = np.asarray(self.lower)
                    upper_arr = np.asarray(self.upper)
                    ci_x = np.concatenate([[anchor_x], fc_x])
                    ci_lower = np.concatenate([[lower_arr[first_oos - 1]], fc_lower])
                    ci_upper = np.concatenate([[upper_arr[first_oos - 1]], fc_upper])

                ax.fill_between(
                    ci_x,
                    ci_lower,
                    ci_upper,
                    color=DEFAULT_PALETTE[4],
                    alpha=0.15,
                    linewidth=0,
                    label="Forecast 95% CI",
                )

            # Layer 5: forecast start divider
            ax.axvline(
                x=forecast_start,
                color=DEFAULT_PALETTE[1],
                linestyle="--",
                linewidth=1.0,
                alpha=0.7,
            )
        elif not has_any:
            ax.plot(
                np.arange(len(self.mean)),
                np.asarray(self.mean),
                color=DEFAULT_PALETTE[0],
                linestyle="-",
                linewidth=1.5,
                label="Predicted",
            )
            has_any = True

        style_axes(ax)
        ax.set_xlabel("Time", fontsize=AXIS_LABEL_FONTSIZE)
        ax.set_ylabel("Value", fontsize=AXIS_LABEL_FONTSIZE)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))

        if title is None:
            title = "Prediction Results"
        ax.set_title(title, fontsize=TITLE_FONTSIZE, fontweight="bold")

        if xlim is not None:
            ax.set_xlim(xlim)

        if has_any:
            ax.legend(frameon=False, fontsize=14)

        fig.tight_layout(pad=1.5)
        return fig, ax


@dataclass
class BaseModelResult:
    """Common result container for all TsModel model estimation results.

    Subclasses add model-specific fields and methods (predict, forecast, etc.).

    Parameters
    ----------
    model_type : str
        Model identifier (e.g. ``"SARIMA"``, ``"ARCH"``, ``"GARCH"``).
    params : dict
        Estimated parameter values keyed by name.
    std_errors : dict
        Standard errors keyed by parameter name.
    p_values : dict
        p-values keyed by parameter name.
    aic : float
        Akaike Information Criterion.
    bic : float
        Bayesian Information Criterion.
    log_likelihood : float
        Maximised log-likelihood.
    residuals : np.ndarray
        Residual series (length *nobs*).
    fitted_values : np.ndarray or None
        Fitted values (length *nobs*). May be ``None`` for pure volatility
        models.
    nobs : int
        Effective number of observations used in estimation.
    data : np.ndarray
        Original input data series.
    """

    model_type: str
    params: dict
    std_errors: dict
    p_values: dict
    aic: float
    bic: float
    log_likelihood: float
    residuals: np.ndarray
    fitted_values: np.ndarray | None
    nobs: int
    data: np.ndarray

    def summary(self) -> str:
        """Return a formatted parameter summary string.

        Returns
        -------
        str
        """
        lines = [
            f"{self.model_type} Model Estimation Result",
            "=" * 50,
            f"Observations       : {self.nobs}",
            f"Log-Likelihood     : {self.log_likelihood:.4f}",
            f"AIC                : {self.aic:.4f}",
            f"BIC                : {self.bic:.4f}",
            "",
            "Parameter Estimates:",
            "-" * 50,
        ]
        for name in self.params:
            val = self.params[name]
            se = self.std_errors.get(name)
            pv = self.p_values.get(name)
            se_str = f"{se:.4f}" if se is not None else "N/A"
            pv_str = f"{pv:.4f}" if pv is not None else "N/A"
            lines.append(f"  {name:<20s} {val:>10.4f}  ({se_str})  p={pv_str}")
        return "\n".join(lines)

    def plot_fit(self, title=None):
        """Plot actual vs fitted values.

        Uses :func:`TsPlots.plot_series` for unified styling.

        Parameters
        ----------
        title : str, optional
            Chart title.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        from Ts.TsPlots import plot_series

        if title is None:
            title = f"{self.model_type}: Actual vs Fitted"

        plot_data = {"Actual": self.data}
        if self.fitted_values is not None:
            plot_data["Fitted"] = self.fitted_values

        fig, ax = plot_series(
            plot_data,
            title=title,
            ytitle="Value",
            xtitle="Time",
        )
        return fig, ax

    def plot_diagnostics(self, title=None):
        """Plot diagnostic charts: residuals, ACF, PACF.

        Three-panel figure: residuals over time, residual ACF, residual PACF.
        The residuals panel includes white noise and normality test results.

        Parameters
        ----------
        title : str, optional
            Suptitle for the figure.

        Returns
        -------
        fig : matplotlib.figure.Figure
        axes : numpy.ndarray of matplotlib.axes.Axes
        """
        import matplotlib.pyplot as plt

        from Ts.TsPlots import plot_acf, plot_pacf, plot_series

        if title is None:
            title = f"{self.model_type}: Diagnostic Plots"

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 10))

        plot_series(
            self.residuals,
            ax=ax1,
            title="Residuals",
            ytitle="Residual",
            show_legend=False,
        )

        # Run white noise and normality tests for annotation
        from Ts.TsTests import LjungBoxTest, NormalityTest

        wn_lags = min(10, max(1, len(self.residuals) // 5))
        wn = LjungBoxTest(self.residuals, lags=wn_lags, apply_squared=False)
        wn_result = wn.fit()
        nm = NormalityTest(self.residuals)
        nm_result = nm.fit()

        anno_lines = [
            f"White Noise: Q({wn_result.lags})={wn_result.statistic:.2f}, p={wn_result.pvalue:.3f}",
            f"Normality: JB={nm_result.statistic:.2f}, p={nm_result.pvalue:.3f}",
        ]
        anno_text = "\n".join(anno_lines)
        ax1.text(
            0.98,
            0.95,
            anno_text,
            transform=ax1.transAxes,
            fontsize=8,
            ha="right",
            va="top",
            bbox={
                "boxstyle": "round,pad=0.3",
                "facecolor": "white",
                "alpha": 0.85,
                "edgecolor": "#cccccc",
            },
        )

        plot_acf(self.residuals, ax=ax2, title="Residual ACF")

        plot_pacf(self.residuals, ax=ax3, title="Residual PACF")

        fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.tight_layout()
        return fig, (ax1, ax2, ax3)

    def test_residuals(self, lags=10):
        """Run residual diagnostic tests.

        Executes four tests:
        - White noise: Ljung-Box on raw residuals (H0: no autocorrelation)
        - Normality: Jarque-Bera (H0: normally distributed)
        - ARCH effects: Ljung-Box on squared residuals (H0: no ARCH)
        - ARCH effects: Engle LM (H0: no ARCH)

        Parameters
        ----------
        lags : int
            Number of lags for autocorrelation-based tests.

        Returns
        -------
        ResidualTestResults
            Container with ``.white_noise``, ``.normality``, ``.ljung_box``,
            `.engle_lm` attributes and supports `print()` for a formatted
            summary with detailed output.
        """
        from Ts.TsTests import EngleLMTest, LjungBoxTest, NormalityTest

        wn = LjungBoxTest(self.residuals, lags=lags, apply_squared=False)
        wn_result = wn.fit()

        norm = NormalityTest(self.residuals)
        norm_result = norm.fit()

        lb = LjungBoxTest(self.residuals, lags=lags)
        lb_result = lb.fit()

        lm = EngleLMTest(self.residuals, lags=lags)
        lm_result = lm.fit()

        return ResidualTestResults(
            white_noise=wn_result,
            normality=norm_result,
            ljung_box=lb_result,
            engle_lm=lm_result,
        )

    def long_run_equilibrium(self):
        """Return the long-run equilibrium of the estimated model.

        Subclasses override this to return the appropriate long-run concept:

        - **SARIMA** (stationary, no differencing): unconditional mean
          :math:`E[y_t]` (``float``).
        - **VAR** (stable, no time trend): unconditional mean vector
          :math:`E[\\mathbf{y}_t]` (``np.ndarray`` of shape ``(k,)``).
        - **GARCH** / **GJR-GARCH** (covariance stationary): unconditional
          variance :math:`\\operatorname{Var}[\\varepsilon_t]` (``float``).

        Returns ``None`` when the concept is not applicable (non-stationary,
        deterministic trend, differenced series, EGARCH, IGARCH, etc.).

        Returns
        -------
        float or np.ndarray or None
            The long-run equilibrium value, or ``None`` if not applicable.
        """
        return


@dataclass
class ResidualTestResults:
    """Container for residual diagnostic test results.

    Wraps white noise, normality, Ljung-Box, and Engle LM test results.

    Parameters
    ----------
    white_noise : LjungBoxTestResult
        Ljung-Box Q-test on raw residuals (H0: no autocorrelation).
    normality : NormalityTestResult
        Jarque-Bera normality test.
    ljung_box : LjungBoxTestResult
        Ljung-Box Q-test on squared residuals (H0: no ARCH effects).
    engle_lm : EngleLMTestResult
        Engle LM test for ARCH effects.
    """

    white_noise: object
    normality: object
    ljung_box: object
    engle_lm: object

    def __str__(self) -> str:
        wn = self.white_noise
        nm = self.normality
        lb = self.ljung_box
        lm = self.engle_lm

        wn_conc = "Autocorrelation" if wn.pvalue < 0.05 else "White noise"
        nm_conc = "Non-normal" if nm.pvalue < 0.05 else "Normal"
        lb_conc = "ARCH effects" if lb.pvalue < 0.05 else "No ARCH effects"
        lm_conc = "ARCH effects" if lm.pvalue < 0.05 else "No ARCH effects"

        lines = [
            "Residual Diagnostic Tests",
            "=" * 75,
            f"{'Test':<28s} {'Statistic':>10s} {'p-value':>10s}  Conclusion",
            "-" * 75,
            f"{'White Noise (Ljung-Box)':<28s} {wn.statistic:>10.3f} {wn.pvalue:>10.4f}  {wn_conc}",
            f"{'Normality (Jarque-Bera)':<28s} {nm.statistic:>10.3f} {nm.pvalue:>10.4f}  {nm_conc}",
            f"{'ARCH Effect (Ljung-Box)':<28s} {lb.statistic:>10.3f} {lb.pvalue:>10.4f}  {lb_conc}",
            f"{'ARCH Effect (Engle LM)':<28s} {lm.statistic:>10.3f} {lm.pvalue:>10.4f}  {lm_conc}",
            "",
            "-" * 75,
            "",
            str(wn),
            "",
            str(nm),
            "",
            str(lb),
            "",
            str(lm),
        ]
        return "\n".join(lines)

    def summary(self) -> str:
        """Return formatted summary string (same as ``__str__``)."""
        return str(self)


class BaseModel(ABC):
    """Abstract base class for all time series models in TsModel.

    Every model must implement :meth:`fit` and expose a :attr:`result_`
    attribute. The :meth:`summary` method returns a formatted string.
    """

    result_: BaseModelResult | None = None

    @abstractmethod
    def fit(self) -> BaseModelResult:
        """Estimate the model and return a result object.

        The result is also stored in :attr:`result_`.
        """
        ...

    _evaluation_target_name = "observed"
    _backcast_target_name = "observed"

    def _clone_for_evaluation(self, data, exog=None, *, dates=None):
        """Clone this configuration with an isolated evaluation data window."""
        cloned = copy.copy(self)
        cloned.data = np.array(data, dtype=float, copy=True)
        cloned.result_ = None
        if hasattr(cloned, "dropped_positions"):
            cloned.dropped_positions = ()
        if hasattr(cloned, "exog"):
            cloned.exog = (
                None if exog is None else np.array(exog, dtype=float, copy=True)
            )
        if hasattr(cloned, "dates"):
            cloned.dates = None if dates is None else dates.copy()
        return cloned

    def _evaluation_predict_kwargs(self, start, stop):
        """Return model-specific context for an evaluation forecast window."""
        del start, stop
        return {}

    def _evaluation_actual(self, observed, train_data):
        """Return the observable target used to score forecasts."""
        del train_data
        return np.array(observed, dtype=float, copy=True)

    def _validate_evaluation(self, context):
        """Validate model-specific requirements for an evaluation method."""
        del context

    def oos(
        self,
        estimation_period,
        validation_period,
        *,
        alpha=0.05,
    ):
        """Evaluate an explicit validation period after isolated estimation."""
        from Ts.TsMetrics import oos

        return oos(
            self,
            estimation_period=estimation_period,
            validation_period=validation_period,
            alpha=alpha,
        )

    def backtest(
        self,
        initial_window,
        *,
        horizon=1,
        step=1,
        window="expanding",
        window_size=None,
        alpha=0.05,
        on_error="raise",
    ):
        """Run leakage-free rolling-origin forecast evaluation.

        A fresh model is fitted at every origin using only observations
        available before that origin. The configured model and any existing
        ``result_`` are left unchanged.

        Parameters
        ----------
        initial_window : int
            Number of observations available at the first forecast origin.
        horizon : int
            Number of periods predicted from each origin.
        step : int
            Distance between consecutive forecast origins.
        window : {expanding, rolling}
            Training-window update rule.
        window_size : int, optional
            Fixed rolling-window length, between 10 and ``initial_window``.
            Defaults to ``initial_window``.
        alpha : float
            Significance level used for prediction intervals.
        on_error : {raise, record}
            Whether a failed window stops evaluation or is recorded as NaN.

        Returns
        -------
        BacktestResult
        """
        from Ts.TsMetrics import backtest

        return backtest(
            self,
            initial_window=initial_window,
            horizon=horizon,
            step=step,
            window=window,
            window_size=window_size,
            alpha=alpha,
            on_error=on_error,
        )

    def backcast(self, steps, alpha=0.05):
        """Estimate pre-sample values by reverse-time refitting.

        The observed series is reversed, the same configured model is fitted
        to that reversed series, and its forecasts are reversed back into
        chronological pre-sample order. Deterministic trends are therefore
        re-estimated in reverse time. This is a statistical reconstruction,
        not a causal claim about unobserved history.

        Parameters
        ----------
        steps : int
            Number of pre-sample periods to estimate.
        alpha : float
            Significance level used for prediction intervals.

        Returns
        -------
        BackcastResult
        """
        from Ts.TsModels._backcast import backcast_model

        return backcast_model(self, steps=steps, alpha=alpha)

    def summary(self) -> str:
        """Return a formatted summary string.

        Automatically calls :meth:`fit` if :attr:`result_` is ``None``.
        """
        if self.result_ is None:
            self.fit()
        return self.result_.summary()
