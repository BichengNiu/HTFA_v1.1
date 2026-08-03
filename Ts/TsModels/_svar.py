"""SVAR — Structural Vector Autoregression estimation.

Provides :class:`SVAR` and :class:`SVARResult` for short-run (A/B)
and long-run (Blanchard-Quah) identified structural VAR models.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
from numpy.linalg import det
from scipy.optimize import minimize

from Ts.TsUtils._validation import _resolve_missing_rows

from Ts.TsModels._base import (
    BaseModel,
    _normalise_model_dates,
)
from Ts.TsModels._var import VAR, IRFResult, VARResult


def _param_to_matrices(params, A_mask, B_mask, A_template, B_template):
    """Fill *params* back into *A_template* and *B_template* using masks.

    Parameters
    ----------
    params : np.ndarray
        Flat parameter vector ``[A_free..., B_free...]``.
    A_mask : np.ndarray (bool)
        True where A has a free parameter.
    B_mask : np.ndarray (bool)
        True where B has a free parameter.
    A_template : np.ndarray
        Template A matrix (fixed values + NaN at free positions).
    B_template : np.ndarray
        Template B matrix.

    Returns
    -------
    A : np.ndarray
    B : np.ndarray
    """
    A = A_template.copy()
    B = B_template.copy()
    n_a = np.sum(A_mask)
    if n_a > 0:
        A[A_mask] = params[:n_a]
    if np.sum(B_mask) > 0:
        B[B_mask] = params[n_a:]
    return A, B


def _nll_ab(params, A_mask, B_mask, A_template, B_template, sigma_u, nobs):
    """Negative concentrated log-likelihood for the AB-model.

    Parameters
    ----------
    params : np.ndarray
        Free structural parameters ``[A_free..., B_free...]``.
    A_mask, B_mask : np.ndarray (bool)
        Masks for A and B free positions.
    A_template, B_template : np.ndarray
        Template matrices.
    sigma_u : np.ndarray
        Reduced-form residual covariance (k, k).
    nobs : int
        Effective number of observations.

    Returns
    -------
    float
        Negative log-likelihood value.
    """
    A, B = _param_to_matrices(params, A_mask, B_mask, A_template, B_template)

    A_det = det(A)
    B_det = det(B)
    if np.isclose(A_det, 0.0) or np.isclose(B_det, 0.0):
        return 1e20

    W = np.linalg.solve(B, A)  # B^{-1} A
    trace_term = np.trace(W.T @ W @ sigma_u)

    return (
        -nobs * np.log(np.abs(A_det))
        + nobs * np.log(np.abs(B_det))
        + 0.5 * nobs * trace_term
    )


def _solve_blanchard_quah(sigma_u, coefs):
    """Blanchard-Quah long-run identification via Cholesky on long-run
    covariance.

    For a k-variable VAR(p) with coefficient matrices ``A_1,...,A_p``:

    .. math::

        \\Psi(1) = (I - A_1 - ... - A_p)^{-1}
        S_{lr} = \\Psi(1) \\Sigma_u \\Psi(1)^T
        C = \\operatorname{chol}(S_{lr})
        B = \\Psi(1)^{-1} C

    Parameters
    ----------
    sigma_u : np.ndarray
        Reduced-form residual covariance (k, k).
    coefs : np.ndarray
        VAR coefficient matrices, shape ``(lags, k, k)``.

    Returns
    -------
    B : np.ndarray
        Structural impact matrix (k, k).
    """
    k = sigma_u.shape[0]
    A_sum = np.sum(coefs, axis=0)  # (k, k)
    psi1 = np.linalg.inv(np.eye(k) - A_sum)
    S_lr = psi1 @ sigma_u @ psi1.T
    C = np.linalg.cholesky(S_lr)  # lower triangular
    return np.linalg.solve(psi1, C)


@dataclass
class SVARResult(VARResult):
    """Result container for SVAR model estimation.

    Inherits all fields and methods from :class:`VARResult` and adds
    structural parameters, structural IRF, and structural FEVD.

    Parameters
    ----------
    A : np.ndarray
        Estimated A matrix (k, k).
    B : np.ndarray
        Estimated B matrix (k, k).
    svar_type : str
        ``"AB"`` for short-run or ``"longrun"`` for long-run.
    sigma_u : np.ndarray
        Reduced-form residual covariance matrix (k, k).
    svar_log_likelihood : float
        Log-likelihood of the structural model.
    structural_residuals : np.ndarray
        Structural shocks, shape (nobs, k).
    _sirf_cache : dict or None
        Internal cache for structural IRF computation.
    """

    A: np.ndarray = None
    B: np.ndarray = None
    svar_type: str = "AB"
    sigma_u: np.ndarray = None
    svar_log_likelihood: float = 0.0
    structural_residuals: np.ndarray = None
    _sirf_cache: dict | None = field(default=None, repr=False)

    # Identification metadata for bootstrap CI
    _A_template: np.ndarray | None = field(default=None, repr=False)
    _B_template: np.ndarray | None = field(default=None, repr=False)
    _A_mask: np.ndarray | None = field(default=None, repr=False)
    _B_mask: np.ndarray | None = field(default=None, repr=False)
    _C_lr: np.ndarray | None = field(default=None, repr=False)

    def summary(self) -> str:
        """Return a formatted summary including structural matrices.

        Returns
        -------
        str
        """
        ll_str = (
            f"{self.svar_log_likelihood:.4f}"
            if self.svar_type != "longrun"
            else "(closed-form)"
        )
        lines = [
            f"SVAR ({self.svar_type}) Model Estimation Result",
            "=" * 60,
            f"Variables  : {', '.join(self._data_names)}",
            f"Observations: {self.nobs}",
            f"Log-Likelihood (SVAR): {ll_str}",
            f"AIC         : {self.aic:.4f}",
            f"BIC         : {self.bic:.4f}",
            "",
        ]

        # Compact structural matrices
        if self.A is not None and self.B is not None:
            lines.append("Structural parameters (A @ u = B @ eps):")
            lines.append("-" * 40)
            a_rows = ", ".join(
                "["
                + "  ".join(f"{self.A[i, j]:10.4f}" for j in range(self.A.shape[1]))
                + "]"
                for i in range(self.A.shape[0])
            )
            b_rows = ", ".join(
                "["
                + "  ".join(f"{self.B[i, j]:10.4f}" for j in range(self.B.shape[1]))
                + "]"
                for i in range(self.B.shape[0])
            )
            lines.append(f"  A = [{a_rows}]")
            lines.append(f"  B = [{b_rows}]")
            lines.append("")

        # Per-equation parameter tables
        if self._var_result is not None:
            params_flat = self.params
            se_flat = self.std_errors
            for eq_idx in range(self._k):
                var_name = self._data_names[eq_idx]
                lines.append(f"Equation: {var_name}")
                lines.append("-" * 40)
                for name in sorted(params_flat):
                    parts = name.split(".")
                    eq_var = parts[-1]
                    if eq_var != var_name:
                        continue
                    prefix = parts[0]
                    if prefix in ("const", "trend", "trend2"):
                        continue
                    # Strip redundant dependent-variable suffix
                    display = ".".join(parts[:-1])
                    if len(parts) <= 1:
                        display = name
                    val = params_flat[name]
                    se = se_flat.get(name)
                    pv = self.p_values.get(name)
                    se_s = f"{se:.4f}" if se is not None else "N/A"
                    pv_s = f"{pv:.4f}" if pv is not None else "N/A"
                    lines.append(f"  {display:<30s} {val:>10.4f}  ({se_s})  p={pv_s}")
                for prefix in ("const", "trend", "trend2"):
                    det_name = f"{prefix}.{var_name}"
                    if det_name in params_flat:
                        val = params_flat[det_name]
                        se = se_flat.get(det_name)
                        pv = self.p_values.get(det_name)
                        se_s = f"{se:.4f}" if se is not None else "N/A"
                        pv_s = f"{pv:.4f}" if pv is not None else "N/A"
                        lines.append(
                            f"  {prefix:<30s} {val:>10.4f}  ({se_s})  p={pv_s}"
                        )
                lines.append("")
        return "\n".join(lines)

    def irf(self, periods=10, orth=False, alpha=0.05, n_draws=200, seed=None):
        """Compute impulse response functions.

        Parameters
        ----------
        periods : int
            Number of periods.
        orth : bool
            If False (default), reduced-form IRF.
            If True, **structural** IRF :math:`\\Theta_h = \\Psi_h A^{-1} B`
            with parametric bootstrap confidence bands.
        alpha : float
            Significance level for confidence bands (default 0.05 = 95%).
        n_draws : int
            Number of bootstrap draws (default 200). Only used when
            ``orth=True``.
        seed : int or None
            Random seed for reproducible confidence bands. Only used when
            ``orth=True``.

        Returns
        -------
        IRFResult
            Container with ``.values``, ``.lower``, ``.upper``,
            ``.summary()``, and ``.get()``.
        """
        if not orth:
            return super().irf(periods=periods, orth=False, alpha=alpha)

        # --- structural IRF (A^{-1} B) with bootstrap CI ---
        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")

        cache_hit = (
            self._sirf_cache is not None
            and self._sirf_cache["periods"] == periods
            and self._sirf_cache.get("alpha") == alpha
            and self._sirf_cache.get("n_draws") == n_draws
        )

        if not cache_hit:
            ma = self._var_result.ma_rep(maxn=periods)
            impact = np.linalg.solve(self.A, self.B)
            sirf_vals = np.zeros_like(ma)
            for h in range(periods + 1):
                sirf_vals[h] = ma[h] @ impact

            lower, upper = self._sirf_mc(periods, alpha, n_draws, seed)

            self._sirf_cache = {
                "periods": periods,
                "alpha": alpha,
                "n_draws": n_draws,
                "values": np.asarray(sirf_vals),
                "lower": lower,
                "upper": upper,
            }

        return IRFResult(
            values=self._sirf_cache["values"].copy(),
            lower=self._sirf_cache["lower"].copy(),
            upper=self._sirf_cache["upper"].copy(),
            periods=periods,
            k=self._k,
            names=list(self._data_names),
            orth=True,
            alpha=alpha,
            ci_method="bootstrap",
            label="Structural IRF",
        )

    def plot_irf(self, periods=10, orth=False, alpha=0.05, n_draws=200, seed=None):
        """Plot impulse response functions.

        Parameters
        ----------
        periods : int
            Number of periods.
        orth : bool
            If True, plot structural IRF with bootstrap confidence bands.
        alpha : float
            Significance level (default 0.05 = 95%).
        n_draws : int
            Bootstrap draws for structural IRF (default 200).
        seed : int or None
            Random seed for reproducible bands.

        Returns
        -------
        fig : matplotlib.figure.Figure
        axes : numpy.ndarray of matplotlib.axes.Axes
        """
        return super().plot_irf(
            periods=periods, orth=orth, alpha=alpha, n_draws=n_draws, seed=seed
        )

    def _sirf_mc(self, periods, alpha, n_draws, seed):
        """Parametric bootstrap CI for structural IRFs.

        Draws VAR coefficients from their asymptotic normal distribution,
        recomputes sigma_u and structural parameters for each draw,
        then computes structural IRFs to obtain empirical quantiles.

        Follows the same pattern as :meth:`VARResult._fevd_mc`.

        Parameters
        ----------
        periods : int
            Number of IRF periods.
        alpha : float
            Significance level (e.g. 0.05 for 95% CI).
        n_draws : int
            Number of Monte Carlo draws.
        seed : int or None
            Random seed for reproducibility.

        Returns
        -------
        lower : np.ndarray
            Lower bands, shape ``(periods + 1, k, k)``.
        upper : np.ndarray
            Upper bands, shape ``(periods + 1, k, k)``.
        """
        k = self._k
        lags = self._lags
        fitted = self._var_result

        all_params = np.asarray(fitted.params)  # (n_regressors, k)
        endog = np.asarray(fitted.endog)  # (T, k)
        n_obs = endog.shape[0]
        n_eff = n_obs - lags

        has_const = self._trend != "n"
        has_trend = self._trend in ("ct", "ctt")
        has_trend2 = self._trend == "ctt"
        n_det = int(has_const) + int(has_trend) + int(has_trend2)

        # Build fixed regressor matrix Z
        Z_parts = []
        if has_const:
            Z_parts.append(np.ones((n_eff, 1)))
        if has_trend:
            trend = np.arange(lags + 1, n_obs + 1, dtype=float).reshape(-1, 1)
            Z_parts.append(trend)
        if has_trend2:
            Z_parts.append(trend**2)
        for p in range(lags):
            lag_data = endog[lags - 1 - p : n_obs - 1 - p]
            Z_parts.append(lag_data)
        Z = np.column_stack(Z_parts)  # (n_eff, n_regressors)
        y_eff = endog[lags:]  # (n_eff, k)

        # Coefficient covariance
        beta_flat = all_params.ravel()
        cov_beta = np.asarray(fitted.cov_params())

        # Ensure positive definite
        eigvals = np.linalg.eigvalsh(cov_beta)
        min_ev = np.min(eigvals)
        if min_ev < 1e-15:
            cov_beta = cov_beta + np.eye(len(beta_flat)) * (1e-10 - min_ev)

        rng = np.random.default_rng(seed)

        sirf_draws = np.zeros((n_draws, periods + 1, k, k))
        n_bad = 0

        for d in range(n_draws):
            beta_d = rng.multivariate_normal(beta_flat, cov_beta)
            params_d = beta_d.reshape(all_params.shape)  # (n_regressors, k)

            # Residuals and sigma_u from drawn coefficients
            resid_d = y_eff - Z @ params_d
            sigma_u_d = (resid_d.T @ resid_d) / n_eff

            # --- Re-estimate A, B from sigma_u_d ---
            if self._C_lr is not None:
                # Blanchard-Quah long-run identification
                try:
                    A_mats = []
                    for lag_i in range(lags):
                        start = n_det + lag_i * k
                        A_lag = params_d[start : start + k, :].T
                        A_mats.append(A_lag)
                    coefs_d = np.stack(A_mats)
                    B_d = _solve_blanchard_quah(sigma_u_d, coefs_d)
                    A_d = np.eye(k)
                except (np.linalg.LinAlgError, ValueError):
                    n_bad += 1
                    A_d = self.A
                    B_d = self.B
            else:
                # Short-run A/B model via MLE
                a_mask = self._A_mask
                b_mask = self._B_mask
                n_a = int(np.sum(a_mask)) if a_mask is not None else 0
                n_b = int(np.sum(b_mask)) if b_mask is not None else 0
                n_free = n_a + n_b

                if n_free == 0:
                    A_d = self._A_template
                    B_d = self._B_template
                else:
                    # Cholesky-based initial guess
                    try:
                        L_chol = np.linalg.cholesky(sigma_u_d)
                    except np.linalg.LinAlgError:
                        L_chol = np.eye(k)

                    init_A = self._A_template.copy()
                    init_B = self._B_template.copy()

                    for i in range(k):
                        if b_mask is not None and b_mask[i, i]:
                            init_B[i, i] = max(L_chol[i, i], 0.01)

                    if n_a > 0:
                        for i in range(k):
                            for j in range(k):
                                if a_mask[i, j] and i > j and L_chol[j, j] > 0:
                                    init_A[i, j] = -L_chol[i, j] / L_chol[j, j]

                    if n_b > 0:
                        for i in range(k):
                            for j in range(k):
                                if b_mask is not None and b_mask[i, j] and i != j:
                                    init_B[i, j] = L_chol[i, j]

                    init_params = []
                    if n_a > 0:
                        init_params.extend(init_A[a_mask])
                    if n_b > 0:
                        init_params.extend(init_B[b_mask])
                    init_params = np.asarray(init_params, dtype=float)

                    try:
                        res = minimize(
                            _nll_ab,
                            init_params,
                            args=(
                                a_mask,
                                b_mask,
                                self._A_template,
                                self._B_template,
                                sigma_u_d,
                                n_eff,
                            ),
                            method="BFGS",
                        )
                        if res.success:
                            A_d, B_d = _param_to_matrices(
                                res.x,
                                a_mask,
                                b_mask,
                                self._A_template,
                                self._B_template,
                            )
                        else:
                            n_bad += 1
                            A_d = self.A
                            B_d = self.B
                    except (np.linalg.LinAlgError, ValueError):
                        n_bad += 1
                        A_d = self.A
                        B_d = self.B

            # --- MA coefficients via recursion ---
            A_mats = []
            for lag_i in range(lags):
                start = n_det + lag_i * k
                A_lag = params_d[start : start + k, :].T  # (k, k)
                A_mats.append(A_lag)

            ma_coefs = [np.eye(k)]  # Psi_0 = I
            for h in range(1, periods + 1):
                psi_h = np.zeros((k, k))
                for j in range(1, min(h, lags) + 1):
                    psi_h += A_mats[j - 1] @ ma_coefs[h - j]
                ma_coefs.append(psi_h)

            # --- Structural IRF ---
            try:
                impact = np.linalg.solve(A_d, B_d)
            except np.linalg.LinAlgError:
                n_bad += 1
                impact = np.linalg.solve(self.A, self.B)

            for h in range(periods + 1):
                sirf_draws[d, h] = ma_coefs[h] @ impact

        if n_bad > 0:
            warnings.warn(
                f"Structural IRF bootstrap: {n_bad}/{n_draws} draws "
                f"failed to converge. Using point estimates for "
                f"those draws.",
                RuntimeWarning,
                stacklevel=2,
            )

        lower = np.percentile(sirf_draws, alpha / 2.0 * 100.0, axis=0)
        upper = np.percentile(sirf_draws, (1.0 - alpha / 2.0) * 100.0, axis=0)
        return lower, upper

    def __repr__(self) -> str:
        return self.summary()


class SVAR(BaseModel):
    """Structural Vector Autoregression (SVAR) model estimation.

    Parameters
    ----------
    data : array-like
        Time series data, shape (nobs, k).
    lags : int
        Number of lags (>= 1).
    A : np.ndarray, optional
        Short-run restriction matrix for A (k x k).
        ``np.nan`` marks free parameters; numeric values are fixed.
    B : np.ndarray, optional
        Short-run restriction matrix for B (k x k).
    C_lr : np.ndarray, optional
        Canonical Blanchard-Quah long-run restriction matrix (k x k).
        Strict upper-triangular entries must be zero; diagonal and lower-
        triangular entries must be ``np.nan`` (free). Other restriction
        patterns are not implemented.
    trend : str
        Trend specification (``"c"``, ``"ct"``, ``"ctt"``, ``"n"``).
    cols : list of str, optional
        Variable names.
    dates : datetime-like sequence, optional
        Strict sample dates. A DataFrame DatetimeIndex is inferred automatically.
        Array inputs may provide dates explicitly.
    missing : {"raise", "drop"}
        Non-finite row policy. ``"drop"`` records removed zero-based rows in
        :attr:`dropped_positions`. Default ``"raise"``.

    Notes
    -----
    At least one of ``A`` / ``B`` (short-run) or ``C_lr`` (long-run)
    must be provided.  The AB-model uses MLE via scipy BFGS; the
    long-run model uses the Blanchard-Quah closed-form solution.
    """

    def __init__(
        self,
        data,
        lags=1,
        A=None,
        B=None,
        C_lr=None,
        trend="c",
        cols=None,
        dates=None,
        missing="raise",
    ):
        model_dates = _normalise_model_dates(data, dates, len(data))
        # Column selection must precede np.asarray to get correct shape
        if hasattr(data, "columns"):
            if cols is not None:
                data = data[cols]
            else:
                cols = list(data.columns)

        y = np.asarray(data, dtype=float)
        if y.ndim != 2:
            raise ValueError(f"data must be 2-D (nobs, k), got shape {y.shape}")

        if lags < 1:
            raise ValueError(f"lags must be >= 1, got {lags}")
        if trend not in ("c", "ct", "ctt", "n"):
            raise ValueError(
                f"trend must be one of 'c', 'ct', 'ctt', 'n', got {trend!r}"
            )

        if A is None and B is None and C_lr is None:
            raise ValueError(
                "At least one of A, B (short-run) or C_lr (long-run) must be provided."
            )

        if C_lr is not None and (A is not None or B is not None):
            raise ValueError(
                "C_lr (long-run) is mutually exclusive with A/B (short-run)."
            )

        if cols is not None:
            data_names = list(cols)
        else:
            data_names = [f"y{i}" for i in range(y.shape[1])]

        finite_rows = np.all(np.isfinite(y), axis=1)
        dropped_positions = _resolve_missing_rows(finite_rows, missing)
        if missing == "drop":
            y = y[finite_rows]
            if model_dates is not None:
                model_dates = model_dates[finite_rows].copy()
        else:
            y = y.copy()

        min_obs = lags + 10
        if y.shape[0] < min_obs:
            raise ValueError(
                f"Need at least {min_obs} observations "
                f"({lags} lags + 10), got {y.shape[0]}"
            )

        if A is not None:
            A = np.asarray(A, dtype=float)
            if A.shape != (y.shape[1], y.shape[1]):
                raise ValueError(
                    f"A must be ({y.shape[1]}, {y.shape[1]}), got {A.shape}"
                )
        if B is not None:
            B = np.asarray(B, dtype=float)
            if B.shape != (y.shape[1], y.shape[1]):
                raise ValueError(
                    f"B must be ({y.shape[1]}, {y.shape[1]}), got {B.shape}"
                )
        if C_lr is not None:
            C_lr = np.asarray(C_lr, dtype=float)
            if C_lr.shape != (y.shape[1], y.shape[1]):
                raise ValueError(
                    f"C_lr must be ({y.shape[1]}, {y.shape[1]}), got {C_lr.shape}"
                )
            upper = np.triu_indices(y.shape[1], k=1)
            lower_and_diag = np.tril_indices(y.shape[1])
            if not np.all(C_lr[upper] == 0.0) or not np.all(
                np.isnan(C_lr[lower_and_diag])
            ):
                raise NotImplementedError(
                    "Only the canonical Blanchard-Quah C_lr mask is "
                    "supported: strict upper-triangular entries must be "
                    "0 and diagonal/lower-triangular entries must be np.nan."
                )

        self.data = y
        self.dates = model_dates
        self.missing = missing
        self.dropped_positions = dropped_positions
        self.lags = lags
        self.A = A
        self.B = B
        self.C_lr = C_lr
        self.trend = trend
        self.data_names = data_names

    def fit(self):
        """Estimate the SVAR model.

        First fits the reduced-form VAR, then estimates structural
        parameters via MLE (short-run) or closed-form (long-run).

        Returns
        -------
        SVARResult
        """
        # --- Step 1: reduced-form VAR ---
        var_model = VAR(
            self.data,
            lags=self.lags,
            trend=self.trend,
            cols=self.data_names,
            dates=self.dates,
        )
        var_result = var_model.fit()
        sm_result = var_result._var_result

        k = self.data.shape[1]
        sigma_u = np.asarray(sm_result.sigma_u)
        coefs = np.asarray(sm_result.coefs)  # (lags, k, k)

        # --- Step 2: structural parameters ---
        if self.C_lr is not None:
            # Blanchard-Quah long-run identification
            B_est = _solve_blanchard_quah(sigma_u, coefs)
            A_est = np.eye(k)
            svar_type = "longrun"
            svar_ll = 0.0

            # Store identification metadata for bootstrap CI
            _a_tpl = None
            _b_tpl = None
            _a_mask = None
            _b_mask = None
            _c_lr = self.C_lr.copy()
        else:
            # Short-run A/B model via MLE
            A_tpl = self.A.copy() if self.A is not None else np.eye(k)
            B_tpl = self.B.copy() if self.B is not None else np.eye(k)

            A_mask = np.isnan(A_tpl)
            B_mask = np.isnan(B_tpl)
            A_tpl[A_mask] = 0.0
            B_tpl[B_mask] = 1.0  # initial guess for diagonal elements

            n_free = np.sum(A_mask) + np.sum(B_mask)
            if n_free == 0:
                A_est = A_tpl.copy()
                B_est = B_tpl.copy()
            else:
                # Cholesky-based initial guess
                try:
                    L_chol = np.linalg.cholesky(sigma_u)  # lower
                except np.linalg.LinAlgError:
                    L_chol = np.eye(k)

                init_A = A_tpl.copy()
                init_B = B_tpl.copy()

                # Fill B diagonal from Cholesky diagonal
                for i in range(k):
                    if B_mask[i, i]:
                        init_B[i, i] = max(L_chol[i, i], 0.01)

                # Fill A off-diagonal from Cholesky: A^{-1} B = L
                # For lower-triangular A: A[i,j] = -L[i,j] / L[j,j] (i > j)
                if np.any(A_mask):
                    for i in range(k):
                        for j in range(k):
                            if A_mask[i, j] and i > j and L_chol[j, j] > 0:
                                init_A[i, j] = -L_chol[i, j] / L_chol[j, j]

                # Fill remaining B off-diagonal entries from Cholesky
                if np.any(B_mask):
                    for i in range(k):
                        for j in range(k):
                            if B_mask[i, j] and (i != j):
                                init_B[i, j] = L_chol[i, j]

                init_params = []
                if np.any(A_mask):
                    init_params.extend(init_A[A_mask])
                if np.any(B_mask):
                    init_params.extend(init_B[B_mask])
                init_params = np.asarray(init_params, dtype=float)
                res = minimize(
                    _nll_ab,
                    init_params,
                    args=(A_mask, B_mask, A_tpl, B_tpl, sigma_u, var_result.nobs),
                    method="BFGS",
                )

                if not res.success:
                    warnings.warn(
                        f"SVAR MLE optimization did not converge: "
                        f"{res.message}. Results may be unreliable.",
                        RuntimeWarning,
                        stacklevel=2,
                    )

                A_est, B_est = _param_to_matrices(res.x, A_mask, B_mask, A_tpl, B_tpl)

            # Compute structural log-likelihood
            W = np.linalg.solve(B_est, A_est)
            svar_ll = float(
                var_result.nobs * np.log(np.abs(det(A_est)))
                - var_result.nobs * np.log(np.abs(det(B_est)))
                - 0.5 * var_result.nobs * np.trace(W.T @ W @ sigma_u)
            )
            svar_type = "AB"

            # Store identification metadata for bootstrap CI
            _a_tpl = A_tpl.copy()
            _b_tpl = B_tpl.copy()
            _a_mask = A_mask.copy()
            _b_mask = B_mask.copy()
            _c_lr = None

        # --- Step 3: structural residuals ---
        resid = np.asarray(sm_result.resid)
        u = resid  # reduced-form residuals
        structural_resid = u @ np.linalg.solve(B_est, A_est).T
        # Verify: ε_t = B^{-1} A u_t, so ε = u @ (B^{-1} A)^T

        # --- Step 4: build SVARResult ---
        result = SVARResult(
            model_type="SVAR",
            params=var_result.params,
            std_errors=var_result.std_errors,
            p_values=var_result.p_values,
            aic=var_result.aic,
            bic=var_result.bic,
            log_likelihood=var_result.log_likelihood,
            residuals=var_result.residuals,
            fitted_values=var_result.fitted_values,
            nobs=var_result.nobs,
            data=var_result.data,
            _lags=var_result._lags,
            _data_names=var_result._data_names,
            _k=var_result._k,
            _var_result=var_result._var_result,
            _var_model=var_result._var_model,
            _trend=var_result._trend,
            _irf_cache=var_result._irf_cache,
            A=A_est,
            B=B_est,
            svar_type=svar_type,
            sigma_u=sigma_u,
            svar_log_likelihood=svar_ll,
            structural_residuals=structural_resid,
            _A_template=_a_tpl,
            _B_template=_b_tpl,
            _A_mask=_a_mask,
            _B_mask=_b_mask,
            _C_lr=_c_lr,
        )

        self.result_ = result
        return result

    def summary(self) -> str:
        if self.result_ is None:
            self.fit()
        return self.result_.summary()
