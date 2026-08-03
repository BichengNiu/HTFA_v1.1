"""Perron (1989) unit root test with a known structural break date.

Reference
---------
Perron, P. (1989). "The Great Crash, the Oil Price Shock, and the Unit Root
Hypothesis." *Econometrica*, 57(6), 1361–1401.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import statsmodels.api as sm

from ._base import BaseTest, BaseTestResult
from ._critical_values import _perron_crit
from ._utils import _parse_input, _validate_model
from ._break_utils import (
    _make_break_dummies,
    _select_lags_by_tstat,
    _select_lags_by_ic,
    _build_regression_data,
    _get_regression_columns,
    _extract_rho_stats,
    _extract_coefficients,
)


@dataclass
class PerronTestResult(BaseTestResult):
    """Container for Perron (1989) test results."""

    rho_hat: float = 0.0  # estimated ρ
    rho_se: float = 0.0  # std. error of ρ̂
    break_year: float = 0.0  # break point (in original units)
    break_index: int = 0  # 0-based index of break
    model: str = ""  # "intercept", "slope", or "both"
    cv_01: float = 0.0  # critical value at 1%
    cv_05: float = 0.0  # critical value at 5%
    cv_10: float = 0.0  # critical value at 10%
    coefficients: dict[str, float] = field(default_factory=dict)
    pvalues: dict[str, float] = field(default_factory=dict)
    fitted: np.ndarray | None = None
    rsquared: float = 0.0
    rmse: float = 0.0

    def __str__(self) -> str:
        return (
            f"Perron (1989) Unit Root Test — Model {self.model}\n"
            f"{'=' * 50}\n"
            f"Break point          : {self.break_year}\n"
            f"Number of lags (k)   : {self.lags}\n"
            f"Effective obs. (T)   : {self.nobs}\n"
            f"\n"
            f"ρ̂ (coeff on y_t-1)   : {self.rho_hat:.4f}\n"
            f"s.e.(ρ̂)              : {self.rho_se:.4f}\n"
            f"t(ρ̂) = ρ̂ / s.e.    : {self.statistic:.3f}\n"
            f"\n"
            f"Critical values:\n"
            f"  1%                 : {self.cv_01:.3f}\n"
            f"  5%                 : {self.cv_05:.3f}\n"
            f"  10%                : {self.cv_10:.3f}\n"
            f"\n"
            f"Conclusion (5%): "
            f"{'Reject H0 (stationary with break)' if self.statistic < self.cv_05 else 'Cannot reject H0 (unit root)'}\n"
        )

    @property
    def critical_values(self) -> dict[str, float]:
        """Critical values as a dict, for unified plotting."""
        return {
            "1%": self.cv_01,
            "5%": self.cv_05,
            "10%": self.cv_10,
        }

    def plot_test(self, ax=None):
        """Plot the test statistic against critical values.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            Axes to draw on. Creates a new figure if ``None``.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
        """
        from ._unitroot_plot import _render_critical_value_plot

        return _render_critical_value_plot(self, "Perron (1989)", ax)


class PerronTest(BaseTest):
    """Perron (1989) unit root test with a *known* structural break date.

    Parameters
    ----------
    data : array-like
        The time series to test.
    break_year : float
        The known break date (in the units of *time_index*). The break is
        assumed to occur *after* this observation.
    time_index : array-like, optional
        Time index (e.g., years). If ``None``, a 0-based index is used.
    model : str, optional
        Model specification: ``"intercept"`` (intercept break), ``"slope"`` (trend break),
        or ``"both"`` (both). Default is ``"intercept"``.
    lags : int, optional
        Number of lagged differences (k). If ``None``, automatic selection
        is performed using the method specified by *lag_method*.
    max_lags : int, optional
        Maximum number of lags for automatic selection. Ignored
        if *lags* is provided. Default is 8.
    lag_crit : float, optional
        t-statistic threshold for lag selection (only used when
        *lag_method* is ``"tstat"``). Default is 1.60.
    lag_method : str, optional
        Lag selection method when *lags* is ``None``:
        ``"tstat"`` (default) — general-to-specific t-statistic method;
        ``"aic"`` — minimise AIC over k = 0..max_lags;
        ``"bic"`` — minimise BIC over k = 0..max_lags.

    Attributes
    ----------
    result_ : PerronTestResult
        Full test results after calling :meth:`fit`.
    """

    def __init__(
        self,
        data,
        break_year: float,
        time_index=None,
        model: str = "intercept",
        lags: int | None = None,
        max_lags: int = 8,
        lag_crit: float = 1.60,
        lag_method: str = "tstat",
        y_col=None,
        time_col=None,
    ):
        self.data, self.time_index = _parse_input(data, time_index, y_col, time_col)
        self.break_year = break_year
        _validate_model(model)
        self.model = model
        self.lags = lags
        self.max_lags = max_lags
        self.lag_crit = lag_crit
        if lag_method not in ("tstat", "aic", "bic"):
            raise ValueError(
                f"lag_method must be 'tstat', 'aic', or 'bic', got {lag_method!r}"
            )
        self.lag_method = lag_method
        self.result_: PerronTestResult | None = None

    def fit(self) -> PerronTestResult:
        """Run the Perron (1989) test.

        Returns
        -------
        PerronTestResult
        """
        y = self.data
        T = len(y)
        if not np.all(np.isfinite(y)):
            raise ValueError("Perron test data must contain only finite values.")
        if np.ptp(y) == 0.0:
            raise ValueError("Perron test requires non-constant data.")

        time_idx = self.time_index

        # Locate break index
        break_idx = int(np.argmin(np.abs(time_idx - self.break_year)))
        # Ensure break is not at the very beginning or end
        if break_idx < 2 or break_idx > T - 3:
            warnings.warn(
                f"Break index {break_idx} is near the boundary (T={T}). "
                "Results may be unreliable.",
                stacklevel=2,
            )

        # Create break dummies
        dummies = _make_break_dummies(
            T,
            break_idx,
            self.model,
            include_pulse=True,
        )

        # Lag selection
        if self.lags is None:
            if self.lag_method == "tstat":
                k = _select_lags_by_tstat(
                    y, dummies, self.max_lags, time_idx, self.lag_crit
                )
            else:
                k, _ = _select_lags_by_ic(
                    y, dummies, self.max_lags, time_idx, self.lag_method
                )
        else:
            k = self.lags

        # Build regression data
        df = _build_regression_data(y, dummies, k, time_idx)

        # Define regressors
        reg_cols = _get_regression_columns(dummies, k)

        X = df[reg_cols].values
        y_dep = df["dy"].values

        # OLS estimation
        try:
            res = sm.OLS(y_dep, X).fit()
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as e:
            raise RuntimeError(
                f"Perron test OLS estimation failed. "
                f"This may be caused by singular design matrix "
                f"(e.g., constant or near-constant data). "
                f"Original error: {e}"
            ) from e

        # Extract key statistics
        rho_hat, rho_se, t_stat = _extract_rho_stats(res, reg_cols)

        # Critical values
        cv_01 = _perron_crit(self.model, T, 0.01)
        cv_05 = _perron_crit(self.model, T, 0.05)
        cv_10 = _perron_crit(self.model, T, 0.10)

        # Collect coefficients
        coefs, pvals = _extract_coefficients(res, reg_cols)

        self.result_ = PerronTestResult(
            statistic=t_stat,
            pvalue=None,
            lags=k,
            nobs=len(y_dep),
            residuals=res.resid,
            rho_hat=rho_hat,
            rho_se=rho_se,
            break_year=self.break_year,
            break_index=break_idx,
            model=self.model,
            cv_01=cv_01,
            cv_05=cv_05,
            cv_10=cv_10,
            coefficients=coefs,
            pvalues=pvals,
            fitted=res.fittedvalues,
            rsquared=res.rsquared,
            rmse=np.sqrt(res.mse_resid),
        )
        return self.result_
