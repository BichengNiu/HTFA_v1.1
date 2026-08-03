"""Shared base class for GARCH-family model estimation.

Provides :class:`_BaseVolModel` — parameter validation, fitting dispatch
(standard ARCH/GARCH, IGARCH custom MLE, GARCH-in-Mean), and result
construction.
"""

from __future__ import annotations

import types

import numpy as np
import pandas as pd

from Ts.TsUtils._validation import _resolve_missing_rows

from Ts.TsModels._base import (
    _GARCH_M_FORMS,
    _VOL_TYPES,
    BaseModel,
    _normalise_model_dates,
)
from Ts.TsModels._garch_result import (
    _DIST_LABELS,
    GARCHResult,
    _get_dist_object,
    _scale_params_back,
)


class _BaseVolModel(BaseModel):
    """Shared base for GARCH-family models.

    Handles data validation and the common arch-model fitting logic.
    Supports standard GARCH, GJR-GARCH, GARCH-M (ARCH-in-mean),
    IGARCH (custom MLE), and exogenous regressors.
    """

    _evaluation_target_name = "absolute_demeaned_return_proxy"
    _backcast_target_name = "conditional_volatility"

    def _evaluation_actual(self, observed, train_data):
        """Use absolute returns centred on the active training-window mean."""
        return np.abs(np.asarray(observed, dtype=float) - np.mean(train_data))

    def _validate_evaluation(self, context):
        """Reject evaluation that lacks required future exogenous values."""
        if self.exog is not None:
            raise NotImplementedError(
                f"GARCH {context} with exog requires explicit future "
                "or pre-sample exogenous values"
            )

    def __init__(
        self,
        data,
        p,
        q,
        o=0,
        vol="GARCH",
        mean="Constant",
        dist="normal",
        garch_m=False,
        garch_m_form="vol",
        ar_lags=None,
        exog=None,
        dates=None,
        igarch=False,
        compare_lags=True,
        missing="raise",
    ):
        raw_data = np.asarray(data, dtype=float).ravel()
        model_dates = _normalise_model_dates(data, dates, len(raw_data))
        if exog is not None:
            exog = np.asarray(exog, dtype=float)
            if exog.ndim == 1:
                exog = exog.reshape(-1, 1)
            if exog.shape[0] != len(raw_data):
                raise ValueError(
                    f"exog must have {len(raw_data)} rows (same as data), "
                    f"got {exog.shape[0]}"
                )

        valid_rows = np.isfinite(raw_data)
        if exog is not None:
            valid_rows &= np.all(np.isfinite(exog), axis=1)
        dropped_positions = _resolve_missing_rows(
            valid_rows,
            missing,
            name="data or exog",
        )
        if missing == "drop":
            y = raw_data[valid_rows]
            exog = None if exog is None else exog[valid_rows]
            if model_dates is not None:
                model_dates = model_dates[valid_rows].copy()
        else:
            y = raw_data.copy()

        if p < 1:
            raise ValueError(f"p must be >= 1, got {p}")
        if q < 0:
            raise ValueError(f"q must be >= 0, got {q}")
        if o < 0:
            raise ValueError(f"o must be >= 0, got {o}")
        if vol not in _VOL_TYPES:
            raise ValueError(f"vol must be one of {sorted(_VOL_TYPES)}, got {vol!r}")
        if len(y) < 10:
            raise ValueError(f"Need at least 10 observations, got {len(y)}")
        if garch_m and garch_m_form not in _GARCH_M_FORMS:
            raise ValueError(
                f"garch_m_form must be one of {sorted(_GARCH_M_FORMS)}, "
                f"got {garch_m_form!r}"
            )

        if igarch:
            if vol == "EGARCH":
                raise ValueError(
                    "IGARCH is not supported for EGARCH models. "
                    "Use vol='GARCH' for IGARCH estimation."
                )
            if garch_m:
                raise ValueError("IGARCH is not supported for GARCH-M (garch_m=True).")
            if q < 1:
                raise ValueError(f"IGARCH requires q >= 1 (GARCH component), got q={q}")

        self.data = y
        self.missing = missing
        self.dates = model_dates
        self.dropped_positions = dropped_positions
        self.p = p
        self.q = q
        self.o = o
        self.vol = vol
        self.mean = mean
        self.dist = dist
        self.garch_m = garch_m
        self.garch_m_form = garch_m_form
        self.ar_lags = ar_lags
        self.exog = exog
        self.igarch = igarch
        self.compare_lags = compare_lags

    def fit(self):
        """Estimate the volatility model.

        Returns
        -------
        GARCHResult
        """
        if self.igarch:
            return self._fit_igarch()
        if self.garch_m:
            return self._fit_in_mean()
        return self._fit_standard()

    def _fit_igarch(self):
        """Fit IGARCH(p,q) with constraint sum(alpha) + sum(beta) = 1.

        Uses a custom log-likelihood with the IGARCH constraint imposed
        via reparameterisation: beta_q = 1 - sum(alpha) - sum(beta_{1..q-1}).

        Starting values are obtained from an unconstrained GARCH fit.

        Returns
        -------
        GARCHResult
        """
        from scipy.optimize import minimize

        garch_params = self._fit_standard().params
        if "omega" not in garch_params:
            raise RuntimeError(
                "Unconstrained GARCH initialization did not return omega"
            )
        omega0 = max(garch_params["omega"], 1e-6)
        alpha0 = [max(garch_params[f"alpha[{i}]"], 0.01) for i in range(1, self.p + 1)]
        beta0 = [max(garch_params[f"beta[{j}]"], 0.01) for j in range(1, self.q)]

        x0 = np.array([omega0, *alpha0, *beta0], dtype=float)
        bounds = [(1e-6, None)] + [(1e-6, None)] * (self.p + max(self.q - 1, 0))

        res = minimize(
            self._igarch_nll,
            x0,
            args=(self.data, self.p, self.q),
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 5000},
        )

        if not res.success or not np.isfinite(res.fun):
            raise RuntimeError(f"IGARCH optimization failed to converge: {res.message}")

        std_errors, p_values = self._igarch_std_errors(res.x, self.data, self.p, self.q)

        omega = res.x[0]
        alphas = res.x[1 : 1 + self.p]
        betas_free = res.x[1 + self.p :]
        beta_last = 1.0 - sum(alphas) - sum(betas_free)

        params = {"omega": omega}
        for i, a in enumerate(alphas, 1):
            params[f"alpha[{i}]"] = a
        for j, b in enumerate(betas_free, 1):
            params[f"beta[{j}]"] = b
        if self.q >= 1:
            params[f"beta[{self.q}]"] = beta_last

        sigma2 = self._igarch_recursion(res.x, self.data, self.p, self.q)
        resid = self.data - np.mean(self.data)
        cond_vol = np.sqrt(np.maximum(sigma2, 1e-10))

        n_obs = len(self.data)
        n_params = 1 + self.p + max(self.q - 1, 0)
        loglik = -float(res.fun)
        aic = 2.0 * n_params - 2.0 * loglik
        bic = np.log(n_obs) * n_params - 2.0 * loglik

        param_series = pd.Series(params)
        se_series = pd.Series(std_errors)
        pv_series = pd.Series(p_values)
        dummy_result = types.SimpleNamespace(
            params=param_series,
            std_err=se_series,
            pvalues=pv_series,
            param_cov=None,
            aic=aic,
            bic=bic,
            loglikelihood=loglik,
            resid=resid,
            conditional_volatility=cond_vol,
        )
        result = self._build_result(dummy_result, None, None, None, False)
        self.result_ = result
        return result

    def _igarch_recursion(self, x, data, p, q):
        """Compute IGARCH conditional variances with constraint enforced.

        Parameters
        ----------
        x : np.ndarray
            Free parameters: [omega, alpha_1..alpha_p, beta_1..beta_{q-1}]
        data : np.ndarray
        p : int
        q : int

        Returns
        -------
        np.ndarray
            Conditional variances sigma2_t (length n).
        """
        n = len(data)
        omega = x[0]
        alpha = x[1 : 1 + p]
        beta_free = x[1 + p :]
        beta_last = 1.0 - sum(alpha) - sum(beta_free)
        all_beta = np.append(beta_free, beta_last)

        sigma2 = np.full(n, float(np.var(data)))
        max_lag = max(p, q, 1)
        eps2 = (data - np.mean(data)) ** 2

        for t in range(max_lag, n):
            s2 = omega
            for i in range(p):
                s2 += alpha[i] * eps2[t - 1 - i]
            for j in range(q):
                s2 += all_beta[j] * sigma2[t - 1 - j]
            sigma2[t] = s2

        return sigma2

    def _igarch_nll(self, x, data, p, q):
        """Negative Gaussian log-likelihood for IGARCH with constraint.

        Soft-penalty when derived beta_q < 0.
        """
        beta_last = 1.0 - sum(x[1 : 1 + p]) - sum(x[1 + p :])

        if beta_last < 0:
            return 1e15 * (1.0 - beta_last)

        sigma2 = self._igarch_recursion(x, data, p, q)
        sigma2 = np.maximum(sigma2, 1e-10)
        eps = data - np.mean(data)

        return 0.5 * np.sum(np.log(2.0 * np.pi) + np.log(sigma2) + eps**2 / sigma2)

    def _igarch_std_errors(self, x, data, p, q):
        """Compute standard errors from numerical Hessian at the optimum.

        Parameters
        ----------
        x : np.ndarray
            Optimal free parameters.
        data : np.ndarray
        p, q : int

        Returns
        -------
        std_errors : dict
        p_values : dict
        """
        from scipy.stats import chi2 as chi2_dist

        n_params = len(x)
        eps = 1e-5
        hess = np.zeros((n_params, n_params))
        f0 = self._igarch_nll(x, data, p, q)

        for i in range(n_params):
            xi = x.copy()
            xi[i] += eps
            fi_plus = self._igarch_nll(xi, data, p, q)
            xi[i] -= 2.0 * eps
            fi_minus = self._igarch_nll(xi, data, p, q)
            hess[i, i] = (fi_plus - 2.0 * f0 + fi_minus) / (eps * eps)

            for j in range(i + 1, n_params):
                xpp = x.copy()
                xpp[i] += eps
                xpp[j] += eps
                fpp = self._igarch_nll(xpp, data, p, q)

                xpm = x.copy()
                xpm[i] += eps
                xpm[j] -= eps
                fpm = self._igarch_nll(xpm, data, p, q)

                xmp = x.copy()
                xmp[i] -= eps
                xmp[j] += eps
                fmp = self._igarch_nll(xmp, data, p, q)

                xmm = x.copy()
                xmm[i] -= eps
                xmm[j] -= eps
                fmm = self._igarch_nll(xmm, data, p, q)

                hess[i, j] = (fpp - fpm - fmp + fmm) / (4.0 * eps * eps)
                hess[j, i] = hess[i, j]

        try:
            cov = np.linalg.inv(hess)
        except np.linalg.LinAlgError as error:
            raise np.linalg.LinAlgError(
                "IGARCH Hessian matrix is singular. "
                "Cannot compute standard errors. Try different starting values."
            ) from error
        se = np.sqrt(np.maximum(np.diag(cov), 0.0))

        std_errors = {}
        p_values = {}

        std_errors["omega"] = float(se[0])
        p_values["omega"] = float(
            1.0 - chi2_dist.cdf((x[0] / max(se[0], 1e-10)) ** 2, 1)
        )

        for i in range(p):
            name = f"alpha[{i + 1}]"
            std_errors[name] = float(se[1 + i])
            stat = (x[1 + i] / max(se[1 + i], 1e-10)) ** 2
            p_values[name] = float(1.0 - chi2_dist.cdf(stat, 1))

        for j in range(max(q - 1, 0)):
            name = f"beta[{j + 1}]"
            idx = 1 + p + j
            std_errors[name] = float(se[idx])
            stat = (x[idx] / max(se[idx], 1e-10)) ** 2
            p_values[name] = float(1.0 - chi2_dist.cdf(stat, 1))

        if q >= 1:
            grad = np.ones(n_params)
            grad[0] = 0.0
            var_beta_last = float(grad @ cov @ grad)
            std_errors[f"beta[{q}]"] = float(np.sqrt(max(var_beta_last, 0.0)))
            beta_last = 1.0 - sum(x[1:])
            stat = (beta_last / max(np.sqrt(max(var_beta_last, 0.0)), 1e-10)) ** 2
            p_values[f"beta[{q}]"] = float(1.0 - chi2_dist.cdf(stat, 1))

        return std_errors, p_values

    def _fit_standard(self):
        """Fit standard GARCH/ARCH via :func:`arch.arch_model`."""
        from arch import arch_model

        q_arg = self.q if self.vol == "EGARCH" or self.q > 0 else 1

        am = arch_model(
            self.data,
            x=self.exog,
            mean=self.mean,
            vol=self._vol_type,
            p=self.p,
            o=self.o,
            q=q_arg,
            dist=self.dist,
        )
        fitted = am.fit(disp="off", options={"maxiter": 500})
        if fitted.convergence_flag != 0 or not np.isfinite(fitted.loglikelihood):
            raise RuntimeError(
                "GARCH optimization failed to converge: "
                f"{fitted.optimization_result.message}"
            )

        ind_lags, ind_aic, ind_bic = self._compute_per_lag_ic(fitted)
        result = self._build_result(fitted, ind_lags, ind_aic, ind_bic, self.garch_m)
        self.result_ = result
        return result

    def _fit_in_mean(self):
        """Fit GARCH-M via :class:`arch.univariate.mean.ARCHInMean`."""
        import warnings
        from arch.univariate.mean import ARCHInMean
        from arch.univariate.volatility import GARCH as ArchGARCH, ARCH as ArchARCH

        if self.vol == "EGARCH":
            raise ValueError(
                "GARCH-M is not supported for EGARCH models. "
                "Use vol='GARCH' for ARCH-in-mean estimation."
            )

        mean_lower = self.mean.lower()
        if mean_lower not in ("constant", "zero"):
            raise ValueError(
                f"GARCH-M only supports mean='Constant' or mean='Zero', "
                f"got {self.mean!r}"
            )
        constant = mean_lower == "constant"

        distribution = _get_dist_object(self.dist)
        if distribution is None:
            raise ValueError(
                f"Unsupported distribution for GARCH-M: {self.dist!r}. "
                f"Supported: {sorted(_DIST_LABELS.keys())}"
            )

        if self.q > 0:
            volatility = ArchGARCH(p=self.p, o=self.o, q=self.q)
        else:
            if self.o > 0:
                raise ValueError(
                    "Asymmetric ARCH (o > 0, q = 0) is not supported in "
                    "GARCH-M mode. Use standard GARCH estimation "
                    "(garch_m=False) for asymmetric pure-ARCH models."
                )
            volatility = ArchARCH(p=self.p)

        scale = float(np.std(self.data))
        if scale < 1e-6:
            scale = 1.0
        y_scaled = self.data / scale

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            aim = ARCHInMean(
                y_scaled,
                x=self.exog,
                lags=self.ar_lags,
                constant=constant,
                volatility=volatility,
                distribution=distribution,
                form=self.garch_m_form,
                rescale=False,
            )
            fitted = aim.fit(disp="off")

        _scale_params_back(fitted, scale, self.garch_m_form)

        result = self._build_result(fitted, None, None, None, True)
        self.result_ = result
        return result

    @property
    def _vol_type(self):
        """Volatility model string passed to :func:`arch.arch_model`.

        ``"EGARCH"`` when vol=EGARCH; otherwise ``"GARCH"`` (q > 0)
        or ``"ARCH"`` (q = 0).
        """
        if self.vol == "EGARCH":
            return "EGARCH"
        return "GARCH" if self.q > 0 else "ARCH"

    def _build_result(self, fitted, ind_lags, ind_aic, ind_bic, garch_m):
        """Construct a :class:`GARCHResult` from a fitted arch model."""
        params, std_errors, p_values = self._extract_params(fitted)
        resid = np.asarray(fitted.resid)
        cond_vol = np.asarray(fitted.conditional_volatility)

        if self.igarch:
            model_type = "IGARCH"
        elif self.vol == "EGARCH":
            model_type = "EGARCH"
        elif self.o > 0:
            model_type = "GJR-GARCH"
        else:
            model_type = self._vol_type
        return GARCHResult(
            model_type=model_type,
            dist=self.dist,
            params=params,
            std_errors=std_errors,
            p_values=p_values,
            aic=float(fitted.aic),
            bic=float(fitted.bic),
            log_likelihood=float(fitted.loglikelihood),
            residuals=resid,
            fitted_values=self.data - resid,
            nobs=len(resid),
            data=self.data,
            conditional_volatility=cond_vol,
            _p=self.p,
            _q=self.q,
            _o=self.o,
            _arch_result=fitted,
            individual_lags=ind_lags,
            individual_aic=ind_aic,
            individual_bic=ind_bic,
            garch_m=garch_m,
            garch_m_form=self.garch_m_form,
        )

    def _extract_params(self, fitted):
        """Extract params, std_errors, p_values from a fitted arch result."""
        params = {}
        std_errors = {}
        p_values = {}
        for name in fitted.params.index:
            params[name] = float(fitted.params[name])
            if name in fitted.std_err.index:
                std_errors[name] = float(fitted.std_err[name])
            else:
                std_errors[name] = None
            if name in fitted.pvalues.index:
                p_values[name] = float(fitted.pvalues[name])
            else:
                p_values[name] = None
        return params, std_errors, p_values

    def _compute_per_lag_ic(self, fitted):
        """Compute per-lag AIC/BIC for pure ARCH/EARCH models (q == 0)."""
        if not self.compare_lags or self.q != 0 or self.p <= 1:
            return None, None, None

        import warnings
        from arch import arch_model

        vol_str = self._vol_type
        ind_lags = np.arange(1, self.p + 1, dtype=int)
        ind_aic = np.empty(self.p)
        ind_bic = np.empty(self.p)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for k in range(1, self.p + 1):
                if k == self.p:
                    ind_aic[k - 1] = float(fitted.aic)
                    ind_bic[k - 1] = float(fitted.bic)
                else:
                    q_k = 0 if self.vol == "EGARCH" else 1
                    am_k = arch_model(
                        self.data,
                        x=self.exog,
                        mean=self.mean,
                        vol=vol_str,
                        p=k,
                        o=self.o,
                        q=q_k,
                        dist=self.dist,
                    )
                    f_k = am_k.fit(disp="off")
                    ind_aic[k - 1] = float(f_k.aic)
                    ind_bic[k - 1] = float(f_k.bic)
        return ind_lags, ind_aic, ind_bic
