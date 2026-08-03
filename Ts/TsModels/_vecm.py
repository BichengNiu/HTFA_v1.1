"""VECM — Vector Error Correction Model estimation via statsmodels.

Provides :class:`VECM`, :class:`VECMResult`, and :class:`VECMOrderResult`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats as scipy_stats

from Ts.TsUtils._validation import (
    _resolve_missing_rows,
    validate_alpha as _validate_prediction_alpha,
)

from Ts.TsModels._base import (
    BaseModel,
    BaseModelResult,
    PredictResult,
    _normalise_model_dates,
    _resolve_prediction_window,
)
from Ts.TsModels._var import (
    FEVDResult,
    GrangerCausalityResult,
    IRFResult,
    _GrangerEntry,
    _run_granger_all,
    _stata_fmt,
)

# Map user-facing trend names to statsmodels VECM deterministic.
# Johansen five cases:
#   n         — no constant, no trend (H₂(r))
#   rconstant — constant inside CE only (H₁*(r))  →  "ci"
#   c         — constant outside CE (H₁(r))        →  "co"
#   rtrend    — trend inside CE, constant outside (H*(r))  →  "li"
#   ct        — trend outside, constant outside (H(r))      →  "lo"
_TREND_TO_DETERMINISTIC = {
    "n": "n",
    "rconstant": "ci",
    "c": "co",
    "rtrend": "coli",
    "ct": "colo",
}


def _deterministic_labels(deterministic):
    """Return result labels for deterministic terms outside/inside the CE."""
    outside = []
    inside = []
    if "co" in deterministic:
        outside.append("_cons")
    if "lo" in deterministic:
        outside.append("_trend")
    if "ci" in deterministic:
        inside.append("_cons")
    if "li" in deterministic:
        inside.append("_trend")
    return outside, inside


@dataclass
class VECMOrderResult:
    """Result container for VECM lag-order selection.

    Parameters
    ----------
    selected_lag : int
        Lag length that minimizes the chosen criterion.
    criterion : str
        Criterion used for selection.
    values : dict
        Criterion values per lag.
    endogenous : list of str
        Variable names.
    max_lags : int
        Maximum lags considered.
    nobs : int
        Number of observations used.
    """

    selected_lag: int
    criterion: str
    values: dict
    endogenous: list
    max_lags: int
    nobs: int
    dropped_positions: tuple[int, ...] = ()

    def summary(self) -> str:
        lines = [
            "VECM Lag Order Selection",
            "=" * 60,
            f"Endogenous: {', '.join(self.endogenous)}",
            f"Sample: {self.nobs} observations",
            f"Selection criterion: {self.criterion.upper()}",
            "",
        ]
        hdr = f"{'lag':>4s}  {'criterion':>12s}"
        sep = "-" * 22
        lines.append(hdr)
        lines.append(sep)
        for lag_str, val in self.values.items():
            marker = "*" if int(lag_str) == self.selected_lag else " "
            lines.append(f"{int(lag_str):>4d}  {val:>11.4f}{marker}")
        lines.append(sep)
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.summary()


def _compute_equation_stats(resid_i, fitted_i, n_params_i, nobs):
    """Compute per-equation summary statistics.

    Parameters
    ----------
    resid_i : np.ndarray
        Residuals for equation i, shape (nobs,).
    fitted_i : np.ndarray
        Fitted values for equation i, shape (nobs,).
    n_params_i : int
        Number of parameters in equation i.
    nobs : int
        Effective number of observations.

    Returns
    -------
    dict
        Keys: ``"rmse"``, ``"r_squared"``, ``"chi2"``, ``"p_chi2"``.
    """
    ssr = np.sum(resid_i**2)
    tss = np.sum((fitted_i + resid_i - np.mean(fitted_i + resid_i)) ** 2)
    rmse = float(np.sqrt(ssr / (nobs - n_params_i)))
    r_sq = float(1.0 - ssr / tss) if tss > 1e-15 else 0.0
    # Overall F → chi2 = k * F (Wald test, all coefficients zero)
    if n_params_i > 1 and tss > 1e-15:
        f_stat = ((tss - ssr) / (n_params_i - 1)) / (ssr / (nobs - n_params_i))
        chi2 = f_stat * (n_params_i - 1)
        p_chi2 = float(1.0 - scipy_stats.chi2.cdf(chi2, n_params_i - 1))
    else:
        chi2 = 0.0
        p_chi2 = 1.0
    return {
        "rmse": rmse,
        "r_squared": r_sq,
        "chi2": float(chi2),
        "p_chi2": float(p_chi2),
    }


@dataclass
class VECMResult(BaseModelResult):
    """Result container for VECM estimation.

    Inherits all fields from :class:`BaseModelResult` and adds VECM-specific
    fields for cointegration analysis.

    Parameters
    ----------
    alpha : np.ndarray
        Loading (adjustment) coefficients, shape (k, r).
    beta : np.ndarray
        Cointegrating vectors, shape (k, r).
    gamma : np.ndarray
        Short-run coefficients for lagged differences, shape (k, k*(p-1)).
    sigma_u : np.ndarray
        Residual covariance matrix, shape (k, k).
    coint_rank : int
        Number of cointegrating relations.
    k : int
        Number of endogenous variables.
    _lags : int
        Number of lags in levels.
    _data_names : list of str
        Variable names.
    _vecm_result : object
        Raw statsmodels VECMResults, stored for internal delegation.
    _trend : str
        Trend specification.
    """

    alpha: np.ndarray | None = None
    beta: np.ndarray | None = None
    gamma: np.ndarray | None = None
    sigma_u: np.ndarray | None = None
    coint_rank: int = 1
    k: int = 1
    _lags: int = 2
    _data_names: list | None = None
    _vecm_result: object = None
    _trend: str = "c"

    def summary(self) -> str:
        """Return compact VECM estimation summary.

        Reports header (info criteria), adjustment coefficients (α),
        and cointegrating vectors (β) in bordered table format.
        Short-run dynamics (γ) are available via :meth:`plot_diagnostics`.

        Returns
        -------
        str
        """
        sm = self._vecm_result
        if sm is None:
            return "VECM Result (no fitted statsmodels result)"

        k = self.k
        r = self.coint_rank
        nobs = self.nobs
        names = self._data_names
        z_crit = scipy_stats.norm.ppf(0.975)

        # --- Header ---
        det_sigma = float(np.linalg.det(self.sigma_u))
        lines = [
            "Vector error-correction model",
            f"Sample: {self._lags} - {nobs + self._lags - 1}    "
            f"Obs = {nobs}    AIC = {self.aic:.3f}    BIC = {self.bic:.3f}",
            f"Log-Likelihood = {self.log_likelihood:.4f}    "
            f"Det(Sigma_ml) = {det_sigma:.6f}",
            "",
        ]

        # --- Shared helpers ---
        def _cell(coef, se, is_one=False, is_omitted=False, is_ce_const=False):
            """Format one coefficient cell."""
            if is_ce_const:
                return f"{coef:>10.4f}"
            if is_one:
                return "1.000 (norm) "
            if is_omitted:
                return "0.000 (omit) "
            z = coef / se if se > 0 else 0.0
            sig = "*" if abs(z) > z_crit else " "
            return f"{coef:>10.4f}{sig}({z:>6.2f})"

        def _render_table(label, label_width, col_headers, row_labels, cells):
            """Render a bordered table.

            Parameters
            ----------
            label : str
                Section label (e.g. ``"beta"``).
            label_width : int
                Width of the row-label column.
            col_headers : list of str
                Column headers.
            row_labels : list of str
                Row labels (one per row).
            cells : list of list of str
                cells[row][col] — data cells only (no row label).
            """
            n_cols = len(col_headers)

            # Compute column widths
            col_w = [len(h) for h in col_headers]
            for row in cells:
                for j in range(n_cols):
                    col_w[j] = max(col_w[j], len(row[j]))

            # Separator line
            total = label_width + 3 + sum(col_w) + (n_cols - 1) * 3
            sep = "-" * total
            out_lines = [sep]

            # Header row
            hdr = f" {label:>{label_width}s} |"
            for j in range(n_cols):
                hdr += f"  {col_headers[j]:>{col_w[j]}s}"
            out_lines.append(hdr)

            # Sub-separator
            sub_sep = "-" * label_width + "-+-" + "-" * (total - label_width - 3)
            out_lines.append(sub_sep)

            # Data rows
            for i, row_data in enumerate(cells):
                row = f" {row_labels[i]:>{label_width}s} |"
                for j in range(n_cols):
                    row += f"  {row_data[j]:>{col_w[j]}s}"
                out_lines.append(row)

            out_lines.append(sep)
            return out_lines

        # --- Deterministic helpers ---
        deterministic = _TREND_TO_DETERMINISTIC[self._trend]
        det_out_labels, det_coint_labels = _deterministic_labels(deterministic)
        det_coef = np.asarray(sm.det_coef)
        det_se = np.asarray(sm.stderr_det_coef)
        det_coef_coint = np.asarray(sm.det_coef_coint)
        det_coint_se = np.asarray(sm.stderr_det_coef_coint)

        diff_names = [f"D_{n}" for n in names]

        # --- α table ---
        alpha_cols = [f"_ce{j + 1}" for j in range(r)]
        alpha_cols.extend(det_out_labels)

        alpha_label_w = max(len(d) for d in diff_names)

        alpha_row_labels = []
        alpha_cells = []
        for eq_idx in range(k):
            alpha_row_labels.append(diff_names[eq_idx])
            row_data = []
            for ce_j in range(r):
                coef = self.alpha[eq_idx, ce_j]
                se = sm.stderr_alpha[eq_idx, ce_j]
                row_data.append(_cell(coef, se))
            for det_idx in range(len(det_out_labels)):
                row_data.append(  # noqa: PERF401 - explicit table block
                    _cell(det_coef[eq_idx, det_idx], det_se[eq_idx, det_idx])
                )
            alpha_cells.append(row_data)

        lines.append("Adjustment coefficients (α) — coef (z-stat), * p < 0.05")
        lines += _render_table(
            "", alpha_label_w, alpha_cols, alpha_row_labels, alpha_cells
        )
        lines.append("")

        # --- β table ---
        beta_cols = [f"_ce{j + 1}" for j in range(r)]

        beta_label_w = max(max(len(n) for n in names), 6)

        all_omitted = [
            all(abs(self.beta[v, c]) < 1e-15 for c in range(r)) for v in range(k)
        ]

        beta_row_labels = []
        beta_cells = []
        for var_j in range(k):
            beta_row_labels.append(names[var_j])
            row_data = []
            for ce_j in range(r):
                coef = self.beta[var_j, ce_j]
                se = sm.stderr_beta[var_j, ce_j]
                is_one = abs(coef - 1.0) < 1e-10
                is_omitted = all_omitted[var_j]
                row_data.append(_cell(coef, se, is_one, is_omitted))
            beta_cells.append(row_data)

        for det_idx, label in enumerate(det_coint_labels):
            beta_row_labels.append(label)
            beta_cells.append(
                [
                    _cell(det_coef_coint[det_idx, ce_j], det_coint_se[det_idx, ce_j])
                    for ce_j in range(r)
                ]
            )

        lines.append("Cointegrating vectors (β) — coef (z-stat), * p < 0.05")
        lines += _render_table(
            "beta", beta_label_w, beta_cols, beta_row_labels, beta_cells
        )
        lines.append("")

        return "\n".join(lines)

    def irf(self, periods=10, orth=False, alpha=0.05):
        """Compute impulse response functions.

        Uses the VECM's VAR representation to compute IRFs.

        Parameters
        ----------
        periods : int
            Number of periods.
        orth : bool
            If True, orthogonalized via Cholesky decomposition.
        alpha : float
            Significance level for confidence bands (default 0.05).

        Returns
        -------
        IRFResult
        """
        if self._vecm_result is None:
            raise RuntimeError("No fitted VECM result available")

        k = self.k

        # MA representation from VECM
        ma = self._vecm_result.ma_rep(maxn=periods)
        irf_raw = np.asarray(ma)  # (periods+1, k, k)

        if orth:
            P = np.linalg.cholesky(self.sigma_u)
            vals = irf_raw @ P
        else:
            vals = irf_raw.copy()

        z_crit = scipy_stats.norm.ppf(1.0 - alpha / 2.0)

        # Standard errors for IRF (asymptotic approximation)
        resid_cov = self.sigma_u
        se_vals = np.zeros_like(vals)
        for h in range(periods + 1):
            accum = np.zeros((k, k))
            for s in range(h + 1):
                phi_s = irf_raw[s]
                accum += phi_s @ resid_cov @ phi_s.T
            se_diag = np.sqrt(np.diag(accum))
            se_vals[h] = np.outer(se_diag, np.ones(k))

        lower = vals - z_crit * se_vals
        upper = vals + z_crit * se_vals

        return IRFResult(
            values=vals,
            lower=lower,
            upper=upper,
            periods=periods,
            k=k,
            names=list(self._data_names),
            orth=orth,
            alpha=alpha,
            ci_method="analytic",
        )

    def fevd(self, periods=10):
        """Compute forecast error variance decomposition.

        Uses the VECM's VAR representation via orthogonalized MA coefficients.
        Point estimate only (no confidence bands).

        Parameters
        ----------
        periods : int
            Number of periods.

        Returns
        -------
        FEVDResult
        """
        if self._vecm_result is None:
            raise RuntimeError("No fitted VECM result available")

        k = self.k
        sm = self._vecm_result

        P = np.linalg.cholesky(self.sigma_u)
        orth_ma = sm.orth_ma_rep(maxn=periods, P=P)

        fevd_point = np.zeros((periods, k, k))
        accum = np.zeros((k, k))
        for h in range(periods):
            if h + 1 < len(orth_ma):
                accum += np.asarray(orth_ma[h + 1]) ** 2
            row_sums = accum.sum(axis=1, keepdims=True)
            fevd_point[h] = accum / np.maximum(row_sums, 1e-20)

        return FEVDResult(
            values=fevd_point,
            lower=None,
            upper=None,
            periods=periods,
            k=k,
            names=list(self._data_names),
            method="point",
            alpha=None,
            n_draws=0,
        )

    def granger_causality(self, caused=None, causing=None, kind="f"):
        """Test Granger causality using the VECM's VAR representation.

        Parameters
        ----------
        caused : int or str, optional
            Variable being caused.
        causing : int, str, or list, optional
            Causing variable(s).
        kind : str
            "f" for F-test, "chi2" for chi-squared.

        Returns
        -------
        GrangerCausalityResult
        """
        if self._vecm_result is None:
            raise RuntimeError("No fitted VECM result available")

        if caused is None and causing is None:
            return self._granger_causality_all(kind=kind)
        if caused is None or causing is None:
            raise ValueError(
                "Both 'caused' and 'causing' must be specified, "
                "or neither for all-pairs mode."
            )

        if isinstance(caused, str):
            caused = self._data_names.index(caused)
        if isinstance(causing, str):
            causing = [causing]

        causing_idx = []
        for c in causing if isinstance(causing, list) else [causing]:
            if isinstance(c, str):
                causing_idx.append(self._data_names.index(c))
            else:
                causing_idx.append(c)

        # statsmodels VECM: test_granger_causality(caused, causing, signif)
        sm = self._vecm_result
        sig_level = 0.05
        gc_result = sm.test_granger_causality(caused, causing_idx, sig_level)

        test_stat = float(gc_result.test_statistic)
        p_value = float(gc_result.pvalue)

        df_val = gc_result.df
        if isinstance(df_val, tuple):
            df_val = (int(df_val[0]), int(df_val[1]))
        else:
            df_val = int(df_val)

        entry = _GrangerEntry(
            test_statistic=test_stat,
            p_value=p_value,
            df=df_val,
            caused=self._data_names[caused],
            causing=[self._data_names[i] for i in causing_idx],
        )
        return GrangerCausalityResult(tests=[entry], kind=kind)

    def _granger_causality_all(self, kind="f"):
        """Run all pairwise Granger causality tests (internal)."""
        return _run_granger_all(self, self.k, self._data_names, kind)

    @property
    def is_stable(self):
        """Check if the VECM process is stable.

        Builds the companion matrix from the VECM's VAR representation and
        checks that all eigenvalues are <= 1 in modulus (allow k-r unit roots).
        """
        if self._vecm_result is None:
            raise RuntimeError("No fitted VECM result available")

        k = self.k
        p = self._lags
        var_rep = np.asarray(self._vecm_result.var_rep)
        # var_rep has shape (p, k, k): [A_1, A_2, ..., A_p]
        companion = np.zeros((k * p, k * p))
        for lag_i in range(p):
            companion[:k, lag_i * k : (lag_i + 1) * k] = var_rep[lag_i]
        if p > 1:
            companion[k:, : k * (p - 1)] = np.eye(k * (p - 1))
        evals = np.linalg.eigvals(companion)
        return bool(np.all(np.abs(evals) <= 1.0 + 1e-10))

    def plot_diagnostics(self, title=None):
        """Plot diagnostic charts for each VECM equation.

        Grid: k rows x 3 columns (residuals, ACF, PACF).

        Parameters
        ----------
        title : str, optional

        Returns
        -------
        fig, axes
        """
        import matplotlib.pyplot as plt
        from Ts.TsPlots import plot_series, plot_acf, plot_pacf

        k = self.k
        fig, axes = plt.subplots(k, 3, figsize=(14, 3 * k), squeeze=False)

        for i in range(k):
            name = self._data_names[i]
            plot_series(
                self.residuals[:, i],
                ax=axes[i, 0],
                title=f"D_{name} Residuals",
                ytitle="Residual",
                show_legend=False,
            )
            plot_acf(self.residuals[:, i], ax=axes[i, 1], title=f"D_{name} ACF")
            plot_pacf(self.residuals[:, i], ax=axes[i, 2], title=f"D_{name} PACF")

        if title is None:
            title = f"VECM({self._lags}, r={self.coint_rank}): Diagnostic Plots"
        fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.tight_layout()
        return fig, axes

    def test_residuals(self, lags=10):
        """Run residual diagnostic tests for each equation.

        Parameters
        ----------
        lags : int

        Returns
        -------
        dict
            Mapping from variable name to ResidualTestResults.
        """
        from Ts.TsTests import LjungBoxTest, EngleLMTest, NormalityTest
        from Ts.TsModels._base import ResidualTestResults

        results = {}
        for i in range(self.k):
            name = self._data_names[i]
            resid_i = self.residuals[:, i]
            wn = LjungBoxTest(resid_i, lags=lags, apply_squared=False)
            norm = NormalityTest(resid_i)
            lb = LjungBoxTest(resid_i, lags=lags)
            lm = EngleLMTest(resid_i, lags=lags)
            results[name] = ResidualTestResults(
                white_noise=wn.fit(),
                normality=norm.fit(),
                ljung_box=lb.fit(),
                engle_lm=lm.fit(),
            )
        return results

    def predict(self, start=0, end=None, alpha=0.05):
        """Return in-sample predictions and forecasts beyond the sample.

        Parameters
        ----------
        start : int
            Start index (0-based).
        end : int, optional
            End index. Default: nobs-1.
        alpha : float
            Significance level required by the shared prediction protocol.
            VECM forecasts do not currently include intervals.

        Returns
        -------
        PredictResult
        """
        if self._vecm_result is None:
            raise RuntimeError("No fitted VECM result available")
        nobs = self.nobs
        k = self.k
        window = _resolve_prediction_window(nobs, start, end)
        _validate_prediction_alpha(alpha)
        start, end = window.start, window.end
        fitted = self.fitted_values
        mean = np.full((window.size, k), np.nan)
        lower = None
        upper = None
        is_oos = np.zeros(window.size, dtype=bool)

        if window.has_forecast:
            n_in = window.in_sample_size
            if n_in > 0:
                mean[:n_in] = fitted[start:nobs]
            forecast = np.asarray(
                self._vecm_result.predict(steps=window.forecast_steps)
            )
            mean[n_in:] = forecast[window.forecast_skip :]
            is_oos[n_in:] = True
        else:
            mean = fitted[start : end + 1].copy()

        return PredictResult(
            mean=mean,
            lower=lower,
            upper=upper,
            is_oos=is_oos,
            _full_data=self.data,
            _full_fitted=self.fitted_values,
            _start=start,
        )

    def plot_roots(self, title=None):
        """Plot inverse roots on the complex unit circle.

        Parameters
        ----------
        title : str, optional

        Returns
        -------
        fig, ax
        """
        import matplotlib.pyplot as plt
        from Ts.TsPlots.style import (
            _ensure_fonts,
            DEFAULT_PALETTE,
            style_axes,
            TITLE_FONTSIZE,
            AXIS_LABEL_FONTSIZE,
            TICK_LABELSIZE,
        )

        _ensure_fonts()

        # Use companion matrix eigenvalues from VAR representation
        # Simplified: use gamma eigenvalues
        k = self.k
        companion = np.zeros((k, k))
        companion[:k, :k] = np.eye(k) + self.alpha @ self.beta.T + self.gamma
        roots = np.linalg.eigvals(companion)
        inv_roots = 1.0 / roots

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
        ax.scatter(
            inv_roots.real,
            inv_roots.imag,
            color=DEFAULT_PALETTE[0],
            marker="o",
            s=50,
            edgecolors=DEFAULT_PALETTE[7],
            linewidth=0.5,
            zorder=5,
        )
        ax.set_aspect("equal")
        style_axes(ax)
        ax.set_xlim(-1.3, 1.3)
        ax.set_ylim(-1.3, 1.3)
        ax.set_xlabel("Real", fontsize=AXIS_LABEL_FONTSIZE)
        ax.set_ylabel("Imaginary", fontsize=AXIS_LABEL_FONTSIZE)
        ax.tick_params(labelsize=TICK_LABELSIZE)
        if title is None:
            title = f"VECM({self._lags}, r={self.coint_rank}): Inverse Roots"
        ax.set_title(title, fontsize=TITLE_FONTSIZE, fontweight="bold")
        fig.tight_layout(pad=1.5)
        return fig, ax

    def __repr__(self) -> str:
        return self.summary()


def _add_coef_row(lines, label, coef, se, z_crit):
    """Format a single coefficient row for summary output.

    Parameters
    ----------
    lines : list
        Output lines accumulator.
    label : str
        Row label (e.g. "L1.", "LD.").
    coef : float
        Coefficient value.
    se : float
        Standard error.
    z_crit : float
        Critical z-value for CI.
    """
    z_val = coef / se if abs(se) > 1e-15 else 0.0
    p_val = 2.0 * (1.0 - scipy_stats.norm.cdf(abs(z_val)))
    ci_low = coef - z_crit * se
    ci_high = coef + z_crit * se

    lines.append(
        f"  {label:<8s} | "
        f"{_stata_fmt(coef):>10s}  "
        f"{_stata_fmt(se):>10s}  "
        f"{z_val:>6.2f}  "
        f"{p_val:>6.3f}  "
        f"{_stata_fmt(ci_low):>10s}  "
        f"{_stata_fmt(ci_high):>10s}"
    )


class VECM(BaseModel):
    """Vector Error Correction Model (VECM) estimation.

    Parameters
    ----------
    data : array-like
        Time series data, shape (nobs, k).
    lags : int
        Number of lags in VAR levels (>= 1).
    coint_rank : int
        Cointegration rank (1 <= r < k).
    trend : str
        Trend specification:
        ``"n"`` (none), ``"rconstant"`` (constant in CE),
        ``"c"`` (constant outside CE, default),
        ``"rtrend"`` (trend in CE), ``"ct"`` (trend outside CE).
    cols : list of str, optional
        Variable names for display.
    dates : datetime-like sequence, optional
        Strict sample dates. A DataFrame DatetimeIndex is inferred automatically.
        Array inputs may provide dates explicitly.
    missing : {"raise", "drop"}
        Non-finite row policy. ``"drop"`` records removed zero-based rows in
        :attr:`dropped_positions`. Default ``"raise"``.
    """

    def __init__(
        self,
        data,
        lags=2,
        coint_rank=1,
        trend="c",
        cols=None,
        dates=None,
        missing="raise",
    ):
        model_dates = _normalise_model_dates(data, dates, len(data))
        if hasattr(data, "columns"):
            if cols is not None:
                data = data[cols]
            else:
                cols = list(data.columns)

        y = np.asarray(data, dtype=float)
        if y.ndim != 2:
            raise ValueError(f"data must be 2-D (nobs, k), got shape {y.shape}")

        k = y.shape[1]
        if k < 2:
            raise ValueError(
                f"data must have at least 2 variables (k >= 2), got k = {k}"
            )

        finite_rows = np.all(np.isfinite(y), axis=1)
        dropped_positions = _resolve_missing_rows(finite_rows, missing)
        if missing == "drop":
            y = y[finite_rows]
            if model_dates is not None:
                model_dates = model_dates[finite_rows].copy()
        else:
            y = y.copy()

        if lags < 1:
            raise ValueError(f"lags must be >= 1, got {lags}")
        valid_trends = tuple(_TREND_TO_DETERMINISTIC.keys())
        if trend not in valid_trends:
            raise ValueError(f"trend must be one of {valid_trends}, got {trend!r}")
        if coint_rank < 1 or coint_rank >= k:
            raise ValueError(
                f"coint_rank must be between 1 and {k - 1}, got {coint_rank}"
            )

        min_obs = lags + 10
        if y.shape[0] < min_obs:
            raise ValueError(
                f"Need at least {min_obs} observations "
                f"({lags} lags + 10), got {y.shape[0]}"
            )

        if cols is not None:
            if len(cols) != k:
                raise ValueError(
                    f"cols length ({len(cols)}) must match number of variables ({k})"
                )
            data_names = list(cols)
        else:
            data_names = [f"y{i}" for i in range(k)]

        self.data = y
        self.dates = model_dates
        self.missing = missing
        self.dropped_positions = dropped_positions
        self.lags = lags
        self.coint_rank = coint_rank
        self.trend = trend
        self.data_names = data_names

    @staticmethod
    def select_order(
        data,
        max_lags,
        coint_rank=1,
        criterion="aic",
        cols=None,
        missing="raise",
    ):
        """Select optimal lag length using information criteria.

        Parameters
        ----------
        data : array-like
            Time series data, shape (nobs, k).
        max_lags : int
            Maximum number of lags to consider (>= 1).
        coint_rank : int
            Cointegration rank.
        criterion : str
            Selection criterion: ``"aic"`` or ``"bic"``.
        cols : list of str, optional
            Variable names.

        Returns
        -------
        VECMOrderResult
        """
        valid_criteria = {"aic", "bic"}
        if criterion not in valid_criteria:
            raise ValueError(
                f"criterion must be one of {sorted(valid_criteria)}, got {criterion!r}"
            )
        if max_lags < 1:
            raise ValueError(f"max_lags must be >= 1, got {max_lags}")

        if hasattr(data, "columns"):
            if cols is not None:
                data = data[cols]
            else:
                cols = list(data.columns)

        y = np.asarray(data, dtype=float)
        if y.ndim != 2:
            raise ValueError(f"data must be 2-D (nobs, k), got shape {y.shape}")
        k = y.shape[1]
        finite_rows = np.all(np.isfinite(y), axis=1)
        dropped_positions = _resolve_missing_rows(finite_rows, missing)
        y = y[finite_rows] if missing == "drop" else y.copy()

        names = list(cols) if cols is not None else [f"y{i}" for i in range(k)]

        values = {}
        best_lag = 1
        best_val = float("inf")
        failures = []

        for lag in range(1, max_lags + 1):
            try:
                model = VECM(y, lags=lag, coint_rank=coint_rank, trend="c")
                result = model.fit()
                value = float(getattr(result, criterion))
                if not np.isfinite(value):
                    raise RuntimeError(f"non-finite {criterion.upper()}: {value}")
            except Exception as error:
                value = float("inf")
                failures.append(f"lag {lag}: {type(error).__name__}: {error}")
            values[str(lag)] = value
            if value < best_val:
                best_val = value
                best_lag = lag

        if not np.isfinite(best_val):
            details = "; ".join(failures)
            raise RuntimeError(f"No VECM candidate converged. {details}")

        return VECMOrderResult(
            selected_lag=best_lag,
            criterion=criterion,
            values=values,
            endogenous=names,
            max_lags=max_lags,
            nobs=len(y),
            dropped_positions=dropped_positions,
        )

    def fit(self):
        """Estimate the VECM via MLE.

        Returns
        -------
        VECMResult
        """
        from statsmodels.tsa.vector_ar.vecm import VECM as _SM_VECM

        k = self.data.shape[1]
        r = self.coint_rank
        k_ar_diff = self.lags - 1
        deterministic = _TREND_TO_DETERMINISTIC[self.trend]

        sm_model = _SM_VECM(
            self.data,
            k_ar_diff=k_ar_diff,
            coint_rank=r,
            deterministic=deterministic,
        )
        sm_result = sm_model.fit()

        # Extract results
        alpha = np.asarray(sm_result.alpha)
        beta = np.asarray(sm_result.beta)
        gamma = np.asarray(sm_result.gamma)
        sigma_u = np.asarray(sm_result.sigma_u)
        llf_value = np.real_if_close(sm_result.llf)
        if np.iscomplexobj(llf_value):
            raise RuntimeError(
                f"VECM log-likelihood is unexpectedly complex: {sm_result.llf!r}"
            )
        llf = float(llf_value)
        nobs = int(sm_result.nobs)
        resid = np.asarray(sm_result.resid)
        fitted = np.asarray(sm_result.fittedvalues)

        # Parameter counting for info criteria
        n_params = k * r + (k - r) * r  # alpha + normalized beta
        n_params += k * k * k_ar_diff  # gamma
        n_params += np.asarray(sm_result.det_coef).size
        n_params += np.asarray(sm_result.det_coef_coint).size

        aic = -2.0 * llf + 2.0 * n_params
        bic = -2.0 * llf + n_params * np.log(nobs)

        # Build flat params/std_errors/p_values dicts
        params = {}
        std_errors = {}
        p_values = {}

        # Alpha
        for j in range(r):
            for i in range(k):
                key = f"_ce{j + 1}.D_{self.data_names[i]}"
                params[key] = float(alpha[i, j])
                std_errors[key] = float(sm_result.stderr_alpha[i, j])
                p_values[key] = float(sm_result.pvalues_alpha[i, j])

        # Gamma (short-run)
        gamma_2d = gamma.reshape(k, k * k_ar_diff)
        gamma_se = np.asarray(sm_result.stderr_gamma).reshape(k, k * k_ar_diff)
        gamma_pv = np.asarray(sm_result.pvalues_gamma).reshape(k, k * k_ar_diff)
        for i in range(k):
            for lag_idx in range(k_ar_diff):
                for j in range(k):
                    col = lag_idx * k + j
                    key = f"LD{'' if k_ar_diff == 1 else '.' + str(lag_idx + 1)}.{self.data_names[j]}.D_{self.data_names[i]}"
                    params[key] = float(gamma_2d[i, col])
                    std_errors[key] = float(gamma_se[i, col])
                    p_values[key] = float(gamma_pv[i, col])

        # Deterministic terms outside CE
        det_out_labels, det_coint_labels = _deterministic_labels(deterministic)
        det_coef = np.asarray(sm_result.det_coef)
        det_se = np.asarray(sm_result.stderr_det_coef)
        det_pv = np.asarray(sm_result.pvalues_det_coef)
        for det_idx, label in enumerate(det_out_labels):
            for i in range(k):
                key = f"{label}.D_{self.data_names[i]}"
                params[key] = float(det_coef[i, det_idx])
                std_errors[key] = float(det_se[i, det_idx])
                p_values[key] = float(det_pv[i, det_idx])

        # beta (cointegrating vectors)
        for j in range(r):
            for i in range(k):
                key = f"beta.{self.data_names[i]}.ce{j + 1}"
                params[key] = float(beta[i, j])
                std_errors[key] = float(sm_result.stderr_beta[i, j])
                p_values[key] = float(sm_result.pvalues_beta[i, j])
        # Deterministic terms inside CE
        det_coef_coint = np.asarray(sm_result.det_coef_coint)
        det_coint_se = np.asarray(sm_result.stderr_det_coef_coint)
        det_coint_pv = np.asarray(sm_result.pvalues_det_coef_coint)
        for det_idx, label in enumerate(det_coint_labels):
            for ce_idx in range(r):
                key = f"{label}.ce{ce_idx + 1}"
                params[key] = float(det_coef_coint[det_idx, ce_idx])
                std_errors[key] = float(det_coint_se[det_idx, ce_idx])
                p_values[key] = float(det_coint_pv[det_idx, ce_idx])

        result = VECMResult(
            model_type="VECM",
            params=params,
            std_errors=std_errors,
            p_values=p_values,
            aic=aic,
            bic=bic,
            log_likelihood=llf,
            residuals=resid,
            fitted_values=fitted,
            nobs=nobs,
            data=self.data,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            sigma_u=sigma_u,
            coint_rank=r,
            k=k,
            _lags=self.lags,
            _data_names=self.data_names,
            _vecm_result=sm_result,
            _trend=self.trend,
        )

        self.result_ = result
        return result
