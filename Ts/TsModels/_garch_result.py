"""GARCH model estimation result container.

Provides :class:`GARCHResult` and shared helpers for parameter scaling
and distribution object construction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from Ts.TsUtils._validation import validate_alpha as _validate_prediction_alpha

from Ts.TsModels._base import (
    BaseModelResult,
    PredictResult,
    _resolve_prediction_window,
)

_DIST_LABELS = {
    "normal": "Normal",
    "t": "Student's t",
    "skewt": "Skewed-t",
    "ged": "GED",
}


@dataclass
class GARCHResult(BaseModelResult):
    """Result container for GARCH model estimation.

    Inherits all fields from :class:`BaseModelResult` and adds
    volatility-specific fields and forecasting.

    Parameters
    ----------
    conditional_volatility : np.ndarray or None
        Estimated conditional standard deviation sigma_t (length *nobs*).
    _p : int or None
        ARCH order.
    _q : int or None
        GARCH order (0 for pure ARCH).
    _o : int or None
        Asymmetric (GJR) order (0 for symmetric GARCH).
    _arch_result : object
        Raw arch.univariate.ARCHResult, stored for internal forecast
        delegation.
    """

    conditional_volatility: np.ndarray | None = None
    dist: str = "normal"
    _p: int | None = None
    _q: int | None = None
    _o: int | None = None
    _arch_result: object = None
    individual_lags: np.ndarray | None = None
    individual_aic: np.ndarray | None = None
    individual_bic: np.ndarray | None = None
    garch_m: bool = False
    garch_m_form: str = "vol"

    @property
    def conditional_variance(self) -> np.ndarray:
        """Conditional variance sigma2_t = sigma_t^2.

        Returns
        -------
        np.ndarray
            Squared conditional volatility, length *nobs*.
        """
        return self.conditional_volatility**2

    def summary(self) -> str:
        """Return a formatted parameter summary string.

        Overrides BaseModelResult to add model-type header with order info
        and the IGARCH persistence test (Wald test for sum(alpha)+sum(beta)=1).
        """
        base = super().summary()
        model_label = self.model_type
        if self._o and self._o > 0:
            model_label = (
                f"{model_label}({self._p},{self._o},{self._q if self._q else 0})"
            )
        elif self._q and self._q > 0:
            model_label = f"{model_label}({self._p},{self._q})"
        elif self._p is not None:
            model_label = f"{model_label}({self._p})"

        dist_label = _DIST_LABELS.get(self.dist, self.dist)
        model_label = f"{model_label} [{dist_label}]"

        if self.garch_m:
            model_label = f"{model_label} [ARCH-in-mean, form={self.garch_m_form}]"

        lines = base.split("\n")
        lines[0] = f"{model_label} Model Estimation Result"

        if (
            self._q == 0
            and self.individual_lags is not None
            and self.individual_aic is not None
            and self.individual_bic is not None
        ):
            best_aic = int(self.individual_lags[np.argmin(self.individual_aic)])
            best_bic = int(self.individual_lags[np.argmin(self.individual_bic)])
            lines[4] = (
                f"AIC                : {self.aic:.4f}    Lowest AIC: P = {best_aic}"
            )
            lines[5] = (
                f"BIC                : {self.bic:.4f}    Lowest BIC: P = {best_bic}"
            )

        if (
            self._arch_result is not None
            and getattr(self._arch_result, "param_cov", None) is not None
        ):
            stab = self.test_persistence()
            is_egarch = self.model_type == "EGARCH"
            is_gjr = bool(self._o and self._o > 0)
            if is_egarch:
                h0_label = "sum(beta) = 1"
                sum_label = "sum(beta)"
            elif is_gjr:
                h0_label = "sum(alpha) + 0.5*sum(gamma) + sum(beta) = 1"
                sum_label = "sum(alpha)+0.5*sum(gamma)+sum(beta)"
            else:
                h0_label = "sum(alpha) + sum(beta) = 1"
                sum_label = "sum(alpha) + sum(beta)"
            lines += [
                "",
                f"IGARCH Persistence Test (H0: {h0_label}):",
                "-" * 50,
                f"  {sum_label:<24s} = {stab['persistence_sum']:.4f}",
                f"  Wald chi2(1)          = {stab['chi2']:.4f}",
                f"  p-value               = {stab['pvalue']:.4f}",
            ]

        return "\n".join(lines)

    def predict(self, start=0, end=None, alpha=0.05):
        """Return conditional volatility and forecasts beyond the sample.

        Parameters
        ----------
        start : int
            Start index (0-based).
        end : int, optional
            End index. If > nobs-1, performs out-of-sample forecast.
            Default: nobs-1.
        alpha : float
            Significance level required by the shared prediction protocol.
            GARCH volatility forecasts do not currently include intervals.

        Returns
        -------
        PredictResult
        """
        nobs = self.nobs
        window = _resolve_prediction_window(nobs, start, end)
        _validate_prediction_alpha(alpha)
        start, end = window.start, window.end
        mean = np.full(window.size, np.nan)
        is_oos = np.zeros(window.size, dtype=bool)

        cond_vol = np.asarray(self.conditional_volatility)

        if window.has_forecast:
            n_in = window.in_sample_size
            if n_in > 0:
                mean[:n_in] = cond_vol[start:nobs]

            _, fc_vol = self._forecast(horizon=window.forecast_steps)
            mean[n_in:] = fc_vol[window.forecast_skip :]
            is_oos[n_in:] = True

        else:
            # Pure in-sample
            mean = cond_vol[start : end + 1].copy()

        return PredictResult(
            mean=mean,
            lower=None,
            upper=None,
            is_oos=is_oos,
            _full_data=self.data,
            _full_fitted=None,
            _start=start,
        )

    def _forecast(self, horizon=1):
        """Internal forecast of conditional variance and volatility.

        Parameters
        ----------
        horizon : int
            Forecast horizon (steps ahead).

        Returns
        -------
        variance : np.ndarray
        volatility : np.ndarray
        """
        if self.model_type == "IGARCH":
            return self._forecast_igarch(horizon)

        if self._arch_result is None:
            raise RuntimeError("No fitted arch result available")
        fc = self._arch_result.forecast(horizon=horizon, reindex=False)
        var = np.asarray(fc.variance.values[-1]).ravel()
        vol = np.sqrt(var)
        return var, vol

    def _forecast_conditional_vol(self, start_idx, n_steps):
        """Generate dynamic conditional volatility forecasts from *start_idx*.

        Uses the fitted GARCH parameters and recursion to produce
        *n_steps* of volatility forecasts using only information
        available at *start_idx* - 1.
        """
        resid = np.asarray(self.residuals)
        cond_vol = np.asarray(self.conditional_volatility)

        is_egarch = self.model_type == "EGARCH"
        is_igarch = self.model_type == "IGARCH"

        if is_egarch:
            return self._egarch_forecast_vol(start_idx, n_steps, resid, cond_vol)
        if is_igarch:
            return self._igarch_forecast_vol(start_idx, n_steps, resid, cond_vol)
        return self._garch_forecast_vol(start_idx, n_steps, resid, cond_vol)

    def _garch_forecast_vol(self, start_idx, n_steps, resid, cond_vol):
        """Standard GARCH / GJR-GARCH dynamic volatility forecast."""
        omega = self.params.get("omega", 0.0)
        p = self._p or 0
        q = self._q or 0
        o = self._o or 0

        eps2 = resid**2
        sigma2 = cond_vol**2
        forecasts = np.empty(n_steps)

        for h in range(n_steps):
            s2 = omega
            for i in range(p):
                alpha_i = self.params.get(f"alpha[{i + 1}]", 0.0)
                forecast_idx = h - 1 - i
                if forecast_idx >= 0:
                    shock_variance = forecasts[forecast_idx]
                else:
                    observed_idx = start_idx + h - 1 - i
                    if observed_idx < 0:
                        continue
                    shock_variance = np.nan_to_num(eps2[observed_idx], nan=0.0)
                s2 += alpha_i * shock_variance
            for i in range(o):
                gamma_i = self.params.get(f"gamma[{i + 1}]", 0.0)
                forecast_idx = h - 1 - i
                if forecast_idx >= 0:
                    asymmetric_shock = 0.5 * forecasts[forecast_idx]
                else:
                    observed_idx = start_idx + h - 1 - i
                    if observed_idx < 0:
                        continue
                    indicator = 1.0 if resid[observed_idx] < 0 else 0.0
                    asymmetric_shock = indicator * np.nan_to_num(
                        eps2[observed_idx], nan=0.0
                    )
                s2 += gamma_i * asymmetric_shock
            for j in range(q):
                beta_j = self.params.get(f"beta[{j + 1}]", 0.0)
                forecast_idx = h - 1 - j
                if forecast_idx >= 0:
                    variance = forecasts[forecast_idx]
                else:
                    observed_idx = start_idx + h - 1 - j
                    if observed_idx < 0:
                        continue
                    variance = sigma2[observed_idx]
                s2 += beta_j * variance
            forecasts[h] = s2

        return np.sqrt(np.maximum(forecasts, 0.0))

    def _egarch_forecast_vol(self, start_idx, n_steps, resid, cond_vol):
        """EGARCH dynamic volatility forecast (simplified: use forecast())."""
        if self._arch_result is not None:
            fc = self._arch_result.forecast(
                horizon=n_steps, start=start_idx, reindex=False
            )
            var = np.asarray(fc.variance.values[-1]).ravel()
            return np.sqrt(np.maximum(var, 0.0))
        return np.full(n_steps, np.nan)

    def _igarch_forecast_vol(self, start_idx, n_steps, resid, cond_vol):
        """IGARCH dynamic volatility forecast."""
        sigma2_t = cond_vol[start_idx - 1] ** 2
        eps2_t = resid[start_idx - 1] ** 2

        omega = self.params.get("omega", 0.0)
        p = self._p or 0
        q = self._q or 0

        forecasts = np.empty(n_steps)
        for h in range(n_steps):
            s2 = omega
            for i in range(p):
                alpha_i = self.params.get(f"alpha[{i + 1}]", 0.0)
                if h == 0:
                    s2 += alpha_i * eps2_t
                else:
                    s2 += alpha_i * forecasts[h - 1]
            for j in range(q):
                beta_j = self.params.get(f"beta[{j + 1}]", 0.0)
                if h == 0:
                    s2 += beta_j * sigma2_t
                else:
                    s2 += beta_j * forecasts[h - 1]
            forecasts[h] = s2

        return np.sqrt(np.maximum(forecasts, 0.0))

    def _forecast_igarch(self, horizon):
        """IGARCH forecast: variance grows linearly with horizon.

        For IGARCH(1,1) with alpha+beta=1:
          sigma2_{T+h} = h * omega + sigma2_T

        Parameters
        ----------
        horizon : int

        Returns
        -------
        variance : np.ndarray
        volatility : np.ndarray
        """
        cond_vol = np.asarray(self.conditional_volatility)
        sigma2_t = cond_vol[-1] ** 2

        residuals = np.asarray(self.residuals)
        eps2_t = residuals[-1] ** 2 if len(residuals) > 0 else sigma2_t

        omega = self.params.get("omega", 0.0)

        var = np.empty(horizon)
        for h in range(horizon):
            if h == 0:
                var[h] = omega
                if self._p is not None:
                    for i in range(self._p):
                        alpha_i = self.params.get(f"alpha[{i + 1}]", 0.0)
                        var[h] += alpha_i * eps2_t
                if self._q is not None:
                    for j in range(self._q):
                        beta_j = self.params.get(f"beta[{j + 1}]", 0.0)
                        var[h] += beta_j * sigma2_t
            else:
                var[h] = omega + var[h - 1]

        vol = np.sqrt(np.maximum(var, 0.0))
        return var, vol

    def test_persistence(self):
        """Wald test for IGARCH / non-stationarity boundary.

        Tests whether the estimated volatility persistence equals 1.

        - Standard GARCH / GJR-GARCH: H0 is
          sum(alpha) + 0.5*sum(gamma) + sum(beta) = 1
          (gamma terms have weight 0.5 per the covariance-stationarity
          condition; for symmetric GARCH (o=0), gamma terms are absent
          and this reduces to sum(alpha) + sum(beta) = 1).

        - EGARCH: H0 is sum(beta) = 1
          (only the lagged log-variance coefficients determine
          stationarity in EGARCH; alpha/gamma are not included).

        Uses a Wald chi-squared test with 1 degree of freedom, constructed
        from the covariance matrix of the fitted ``arch`` model.

        Returns
        -------
        dict
            Keys:
            - ``"chi2"`` --- Wald chi-squared test statistic (1 df).
            - ``"pvalue"`` --- p-value from chi-squared(1) distribution.
            - ``"persistence_sum"`` --- estimated persistence sum
              (sum(beta) for EGARCH; weighted sum for GARCH/GJR-GARCH).
            - ``"reject_null"`` --- ``True`` if the null (sum = 1) is
              rejected at the 5 % level, i.e. the model is covariance
              stationary (sum < 1).
            - ``"conclusion"`` --- human-readable interpretation.

        Raises
        ------
        RuntimeError
            If no fitted arch result is available.
        """
        if self._arch_result is None:
            raise RuntimeError("No fitted arch result available")

        is_egarch = self.model_type == "EGARCH"

        if is_egarch:
            beta_names = [f"beta[{j}]" for j in range(1, (self._q or 0) + 1)]
            coef_names = beta_names
            weights = np.ones(len(beta_names))
        else:
            alpha_names = [f"alpha[{i}]" for i in range(1, (self._p or 0) + 1)]
            gamma_names = [f"gamma[{k}]" for k in range(1, (self._o or 0) + 1)]
            beta_names = [f"beta[{j}]" for j in range(1, (self._q or 0) + 1)]
            coef_names = alpha_names + gamma_names + beta_names
            weights = np.array(
                [1.0] * len(alpha_names)
                + [0.5] * len(gamma_names)
                + [1.0] * len(beta_names)
            )

        if not coef_names:
            return {
                "chi2": 0.0,
                "pvalue": 1.0,
                "persistence_sum": 0.0,
                "reject_null": False,
                "conclusion": "No coefficients to test",
            }

        estimates = np.array([self.params.get(name, 0.0) for name in coef_names])
        persistence_sum = float(estimates @ weights)

        vcov = np.asarray(self._arch_result.param_cov)
        param_name_to_idx = {
            name: i for i, name in enumerate(self._arch_result.param_cov.index)
        }
        idx = [
            param_name_to_idx[name] for name in coef_names if name in param_name_to_idx
        ]

        if len(idx) == 0:
            return {
                "chi2": 0.0,
                "pvalue": 1.0,
                "persistence_sum": persistence_sum,
                "reject_null": False,
                "conclusion": "Cannot compute: no coefficients in vcov",
            }

        sub_vcov = vcov[np.ix_(idx, idx)]
        name_to_weight = dict(zip(coef_names, weights, strict=False))
        idx_to_name = {v: k for k, v in param_name_to_idx.items()}
        w = np.array([name_to_weight[idx_to_name[i]] for i in idx])
        var_sum = float(w @ sub_vcov @ w)

        chi2 = 0.0 if var_sum <= 0 else (persistence_sum - 1.0) ** 2 / var_sum

        from scipy import stats as scipy_stats

        pvalue = 1.0 - scipy_stats.chi2.cdf(chi2, 1)
        reject = bool(pvalue < 0.05)

        conclusion = (
            "Reject H0 (sum = 1) -> model is covariance stationary (sum < 1)"
            if reject
            else "Cannot reject H0 (sum = 1) -> possible IGARCH / non-stationary"
        )

        return {
            "chi2": chi2,
            "pvalue": pvalue,
            "persistence_sum": persistence_sum,
            "reject_null": reject,
            "conclusion": conclusion,
        }

    def long_run_equilibrium(self):
        """Return the unconditional variance (long-run volatility level) of
        the estimated GARCH / GJR-GARCH process.

        For a covariance-stationary GARCH:

        .. math::

            \\sigma^2 = \\frac{\\omega}{1 - \\sum\\alpha - \\sum\\beta}

        For GJR-GARCH the denominator includes :math:`0.5\\sum\\gamma`.

        Returns ``None`` when:

        - The model is EGARCH (unconditional variance requires distribution-
          dependent correction).
        - The persistence sum :math:`\\geq 1` (IGARCH or explosive — no
          finite unconditional variance).

        Returns
        -------
        float or None
        """
        # EGARCH unconditional variance requires complex formula
        if self.model_type == "EGARCH":
            return None

        omega = self.params.get("omega", 0.0)
        if omega <= 0.0:
            return None

        # Compute persistence with correct GJR-GARCH weighting
        alpha_sum = sum(
            self.params.get(f"alpha[{i}]", 0.0) for i in range(1, (self._p or 0) + 1)
        )
        gamma_sum = sum(
            self.params.get(f"gamma[{k}]", 0.0) for k in range(1, (self._o or 0) + 1)
        )
        beta_sum = sum(
            self.params.get(f"beta[{j}]", 0.0) for j in range(1, (self._q or 0) + 1)
        )

        if (self._o or 0) > 0:
            persistence = alpha_sum + 0.5 * gamma_sum + beta_sum
        else:
            persistence = alpha_sum + beta_sum

        if persistence >= 1.0 - 1e-10:
            return None

        return omega / (1.0 - persistence)


def _scale_params_back(fitted, scale, form):
    """Transform GARCH-M parameters from scaled data back to original scale.

    Data is scaled by dividing by ``std(data)`` so y_s has unit variance.

    For ``form='var'`` (sigma^2 in mean):
        y_s = y/s, sigma^2_s = sigma^2/s^2
        -> Const* = Const_s * s, kappa* = kappa_s / s, omega* = omega_s * s^2

    For ``form='vol'`` (sigma in mean):
        -> Const* = Const_s * s, kappa* = kappa_s (invariant), omega* = omega_s * s^2

    ``form='log'``:
        -> Const* = Const_s * s, kappa* = kappa_s (invariant), omega* = omega_s * s^2

    alpha, beta, nu: always unchanged.
    """
    s = scale
    s2 = s * s

    _param_scale = {"omega": s2, "kappa": 1.0 / s} if form == "var" else {"omega": s2}

    for name in fitted.params.index:
        mult = _param_scale.get(name)
        if mult is None and (name in ("Const", "mu") or name.startswith("phi")):
            mult = s
        if mult is not None and mult != 1.0:
            fitted.params[name] = float(fitted.params[name]) * mult
            if name in fitted.std_err.index:
                fitted.std_err[name] = float(fitted.std_err[name]) * abs(mult)

    fitted.resid = np.asarray(fitted.resid) * s
    fitted.conditional_volatility = np.asarray(fitted.conditional_volatility) * s


def _get_dist_object(dist):
    """Return an arch distribution object for the given string name.

    Parameters
    ----------
    dist : str
        One of ``"normal"``, ``"t"``, ``"skewt"``, ``"ged"``.

    Returns
    -------
    arch.univariate.distribution.Distribution or None
    """
    from arch.univariate.distribution import (
        Normal,
        StudentsT,
        GeneralizedError,
        SkewStudent,
    )

    mapping = {
        "normal": Normal,
        "t": StudentsT,
        "skewt": SkewStudent,
        "ged": GeneralizedError,
    }
    cls = mapping.get(dist)
    return cls() if cls is not None else None
