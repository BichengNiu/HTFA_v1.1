"""VAR model estimation via statsmodels VAR.

Provides :class:`VAR`, :class:`VARResult`, and :class:`VAROrderResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


def _resolve_name(names, key):
    """Resolve a variable name or integer index to an integer index.

    Parameters
    ----------
    names : list of str
        Variable names.
    key : str or int
        Variable name or index.

    Returns
    -------
    int
    """
    if isinstance(key, str):
        return names.index(key)
    return int(key)


@dataclass
class IRFResult:
    """Impulse response function result container.

    Returned by :meth:`VARResult.irf` and :meth:`VARResult.oirf`.

    Parameters
    ----------
    values : np.ndarray
        IRF array of shape ``(periods + 1, k, k)``.
        ``values[h, i, j]`` = response of variable *i* to shock *j* at horizon *h*.
    lower : np.ndarray or None
        Lower confidence band, same shape as *values*.
    upper : np.ndarray or None
        Upper confidence band, same shape as *values*.
    periods : int
        Number of IRF periods.
    k : int
        Number of endogenous variables.
    names : list of str
        Variable names.
    orth : bool
        Whether the IRF is orthogonalized (Cholesky).
    alpha : float
        Significance level for confidence bands.
    ci_method : str or None
        CI method: ``"analytic"``, ``"bootstrap"``, or ``None`` (no bands).
    """

    values: np.ndarray
    lower: np.ndarray | None
    upper: np.ndarray | None
    periods: int
    k: int
    names: list
    orth: bool
    alpha: float
    ci_method: str | None = None
    label: str | None = None

    def summary(self) -> str:
        """Return a compact Stata-style IRF table with column legend.

        One column per (impulse, response) pair, one row per step.
        Follows the same compact format as :meth:`FEVDResult.summary`.

        Returns
        -------
        str
        """
        if self.label is not None:
            irf_type = self.label
        else:
            irf_type = "Orthogonalized IRF" if self.orth else "IRF"
        ci_pct = int((1 - self.alpha) * 100)
        lines = [
            f"{irf_type} Results ({ci_pct}% CI)",
            "=" * 65,
            f"Variables: {', '.join(self.names)}",
            f"Periods: {self.periods}",
            "",
        ]

        n_cols = self.k * self.k
        col_pairs = [(j, i) for j in range(self.k) for i in range(self.k)]

        # --- column widths ---
        step_w = max(len("step"), len(str(self.periods)))
        val_w = 4
        for h in range(self.periods + 1):
            for j, i in col_pairs:
                val_w = max(val_w, len(_stata_fmt(self.values[h, i, j])))
        for idx in range(1, n_cols + 1):
            val_w = max(val_w, len(f"({idx})"))

        def _step_cell(val):
            return f" {val:<{step_w}} "

        def _val_cell(val):
            return f" {val:>{val_w}} "

        def _row(cells):
            return "|" + "|".join(cells) + "|"

        total_inner = len(_step_cell("")) + len(_val_cell("")) * n_cols + n_cols
        top_border = "+" + "-" * total_inner + "+"
        hdr_sep = (
            "|"
            + "-" * len(_step_cell(""))
            + "+"
            + "+".join("-" * len(_val_cell("")) for _ in range(n_cols))
            + "|"
        )

        lines.append(top_border)

        # header row 1: column numbers
        lines.append(
            _row(
                [_step_cell("")]
                + [_val_cell(f"({idx})") for idx in range(1, n_cols + 1)]
            )
        )
        # header row 2: "step" + col label
        col_label = "sirf" if self.label == "Structural IRF" else "irf"
        lines.append(
            _row([_step_cell("step")] + [_val_cell(col_label) for _ in range(n_cols)])
        )

        lines.append(hdr_sep)

        # data rows (step 0 .. periods)
        for h in range(self.periods + 1):
            lines.append(  # noqa: PERF401 - explicit table rows are clearer
                _row(
                    [_step_cell(str(h))]
                    + [
                        _val_cell(_stata_fmt(self.values[h, i, j]))
                        for j, i in col_pairs
                    ]
                )
            )

        lines.append(top_border)
        lines.append("")

        # --- legend ---
        idx = 1
        for j in range(self.k):
            for i in range(self.k):
                lines.append(
                    f"({idx}) impulse = {self.names[j]}, response = {self.names[i]}"
                )
                idx += 1

        # --- CI note ---
        if self.lower is not None:
            lines.append("")
            if self.ci_method == "analytic":
                band_desc = "Analytic standard errors"
            elif self.ci_method == "bootstrap":
                band_desc = "Residual bootstrap"
            else:
                band_desc = "Confidence bands"
            lines.append(
                f"Note: {band_desc}, "
                f"{(1 - self.alpha) * 100:.0f}% confidence bands."
                f"  Use .lower / .upper to access."
            )
        return "\n".join(lines)

    def get(self, response, shock):
        """Extract IRF values for a specific response-shock pair.

        Parameters
        ----------
        response : str or int
            Response variable name or index.
        shock : str or int
            Shock variable name or index.

        Returns
        -------
        dict
            Keys: ``"step"`` (list of int), ``"value"`` (ndarray),
            ``"lower"`` (ndarray or None), ``"upper"`` (ndarray or None).
        """
        resp_idx = _resolve_name(self.names, response)
        shock_idx = _resolve_name(self.names, shock)
        steps = list(range(self.periods + 1))
        return {
            "step": steps,
            "value": self.values[:, resp_idx, shock_idx],
            "lower": (
                self.lower[:, resp_idx, shock_idx] if self.lower is not None else None
            ),
            "upper": (
                self.upper[:, resp_idx, shock_idx] if self.upper is not None else None
            ),
        }

    def __repr__(self) -> str:
        return self.summary()


@dataclass
class FEVDResult:
    """Forecast error variance decomposition result container.

    Returned by :meth:`VARResult.fevd`.

    Parameters
    ----------
    values : np.ndarray
        FEVD array of shape ``(periods, k, k)``.
        ``values[h, i, j]`` = fraction of variable *i*'s forecast error
        variance attributable to shock *j* at horizon *h* + 1.
    lower : np.ndarray or None
        Lower confidence band, same shape as *values*.
    upper : np.ndarray or None
        Upper confidence band, same shape as *values*.
    periods : int
        Number of FEVD periods.
    k : int
        Number of endogenous variables.
    names : list of str
        Variable names.
    method : str
        CI method (``"mc"`` for Monte Carlo).
    alpha : float or None
        Significance level for confidence bands; `None` for point estimates.
    n_draws : int
        Number of Monte Carlo draws.
    """

    values: np.ndarray
    lower: np.ndarray | None
    upper: np.ndarray | None
    periods: int
    k: int
    names: list
    method: str
    alpha: float | None
    n_draws: int

    def summary(self) -> str:
        """Return a compact Stata-style FEVD table.

        One column per (impulse, response) pair, one row per forecast step.
        A step-0 row (all zeros) is prepended for display only.

        Returns
        -------
        str
        """
        if self.alpha is None:
            title = "FEVD Results (point estimates)"
        else:
            ci_pct = int((1 - self.alpha) * 100)
            title = f"FEVD Results ({ci_pct}% CI)"
        lines = [
            title,
            "=" * 65,
            f"Variables: {', '.join(self.names)}",
            f"Periods: {self.periods}",
            "",
        ]

        n_cols = self.k * self.k
        col_pairs = [(j, i) for j in range(self.k) for i in range(self.k)]

        # --- column widths ---
        step_w = max(len("step"), len(str(self.periods)))
        val_w = len("fevd")
        for h in range(self.periods):
            for j, i in col_pairs:
                val_w = max(val_w, len(_stata_fmt(self.values[h, i, j])))
        for idx in range(1, n_cols + 1):
            val_w = max(val_w, len(f"({idx})"))

        # --- cell helpers ---
        def _step_cell(val):
            return f" {val:<{step_w}} "

        def _val_cell(val):
            return f" {val:>{val_w}} "

        def _row(cells):
            return "|" + "|".join(cells) + "|"

        # --- borders ---
        total_inner = len(_step_cell("")) + len(_val_cell("")) * n_cols + n_cols
        top_border = "+" + "-" * total_inner + "+"
        hdr_sep = (
            "|"
            + "-" * len(_step_cell(""))
            + "+"
            + "+".join("-" * len(_val_cell("")) for _ in range(n_cols))
            + "|"
        )

        # --- table body ---
        lines.append(top_border)

        # header row 1: column numbers
        lines.append(
            _row(
                [_step_cell("")]
                + [_val_cell(f"({idx})") for idx in range(1, n_cols + 1)]
            )
        )
        # header row 2: "step" + "fevd" × n
        lines.append(
            _row([_step_cell("step")] + [_val_cell("fevd") for _ in range(n_cols)])
        )

        lines.append(hdr_sep)

        # step 0 (all zeros, display only)
        lines.append(_row([_step_cell("0")] + [_val_cell("0") for _ in range(n_cols)]))

        # data rows (step 1 .. periods)
        for h in range(self.periods):
            lines.append(  # noqa: PERF401 - explicit table rows are clearer
                _row(
                    [_step_cell(str(h + 1))]
                    + [
                        _val_cell(_stata_fmt(self.values[h, i, j]))
                        for j, i in col_pairs
                    ]
                )
            )

        lines.append(top_border)
        lines.append("")

        # --- legend ---
        idx = 1
        for j in range(self.k):
            for i in range(self.k):
                lines.append(
                    f"({idx}) impulse = {self.names[j]}, response = {self.names[i]}"
                )
                idx += 1

        # --- CI availability note ---
        if self.lower is not None and self.upper is not None:
            lines.append("")
            lines.append(
                f"Note: {ci_pct}% confidence intervals via "
                f"Monte Carlo ({self.n_draws} draws)."
            )

        return "\n".join(lines)

    def get(self, response, shock):
        """Extract FEVD values for a specific response-shock pair.

        Parameters
        ----------
        response : str or int
            Response variable name or index.
        shock : str or int
            Shock variable name or index.

        Returns
        -------
        dict
            Keys: ``"step"`` (list of int, horizon 1..periods),
            ``"value"`` (ndarray), ``"lower"`` (ndarray or None),
            ``"upper"`` (ndarray or None).
        """
        resp_idx = _resolve_name(self.names, response)
        shock_idx = _resolve_name(self.names, shock)
        steps = list(range(1, self.periods + 1))
        return {
            "step": steps,
            "value": self.values[:, resp_idx, shock_idx],
            "lower": (
                self.lower[:, resp_idx, shock_idx] if self.lower is not None else None
            ),
            "upper": (
                self.upper[:, resp_idx, shock_idx] if self.upper is not None else None
            ),
        }

    def __repr__(self) -> str:
        return self.summary()


@dataclass
class VAROrderResult:
    """Result container for VAR lag-order selection.

    Parameters
    ----------
    selected_lag : int
        Lag length that minimizes the chosen criterion.
    criterion : str
        Criterion used for selection (``"aic"``, ``"bic"``, ``"hqic"``, ``"fpe"``).
    criteria_table : dict
        All criteria values: ``{"aic": {lag: val}, "bic": {...}, ...}``.
    endogenous : list of str
        Variable names.
    max_lags : int
        Maximum lags considered.
    nobs : int
        Number of observations used.
    """

    selected_lag: int
    criterion: str
    criteria_table: dict
    endogenous: list = field(default_factory=list)
    max_lags: int = 1
    nobs: int = 0
    dropped_positions: tuple[int, ...] = ()

    def summary(self) -> str:
        """Return a formatted lag-order selection table."""
        max_l = self.max_lags
        table = self.criteria_table

        # Header
        lines = [
            "VAR Lag Order Selection Criteria",
            "=" * 90,
            f"Endogenous: {', '.join(self.endogenous)}",
            f"Sample: {self.nobs} observations",
            f"Selection criterion: {self.criterion.upper()}",
            "",
        ]

        # Column layout
        hdr = (
            f"{'lag':>4s}  "
            f"{'LL':>10s}  "
            f"{'LR':>10s}  "
            f"{'df':>4s}  "
            f"{'p':>8s}  "
            f"{'FPE':>10s}  "
            f"{'AIC':>10s}  "
            f"{'BIC':>10s}  "
            f"{'HQIC':>10s}"
        )
        sep = "-" * len(hdr)
        lines.append(hdr)
        lines.append(sep)

        for lag in range(max_l + 1):
            ll_val = table.get("ll", {}).get(lag)
            lr_val = table.get("lr", {}).get(lag)
            df_val = table.get("df", {}).get(lag)
            p_val = table.get("p", {}).get(lag)
            fpe_val = table.get("fpe", {}).get(lag)
            aic_val = table.get("aic", {}).get(lag)
            bic_val = table.get("bic", {}).get(lag)
            hqic_val = table.get("hqic", {}).get(lag)

            ll_s = f"{ll_val:10.4f}" if ll_val is not None else " " * 10
            lr_s = f"{lr_val:10.4f}" if lr_val is not None else " " * 10
            df_s = f"{int(df_val):4d}" if df_val is not None else " " * 4
            p_s = f"{p_val:8.4f}" if p_val is not None else " " * 8
            fpe_s = f"{fpe_val:10.4e}" if fpe_val is not None else " " * 10
            aic_s = f"{aic_val:10.4f}" if aic_val is not None else " " * 10
            bic_s = f"{bic_val:10.4f}" if bic_val is not None else " " * 10
            hqic_s = f"{hqic_val:10.4f}" if hqic_val is not None else " " * 10

            # Mark the best lag with *
            if lag == self.selected_lag and lag > 0:
                aic_s = f"{aic_val:9.4f}*" if aic_val is not None else " " * 10
                bic_s = f"{bic_val:9.4f}*" if bic_val is not None else " " * 10
                hqic_s = f"{hqic_val:9.4f}*" if hqic_val is not None else " " * 10
                fpe_s = f"{fpe_val:9.4e}*" if fpe_val is not None else " " * 10

            row = (
                f"{lag:>4d}  "
                f"{ll_s:>10s}  "
                f"{lr_s:>10s}  "
                f"{df_s:>4s}  "
                f"{p_s:>8s}  "
                f"{fpe_s:>10s}  "
                f"{aic_s:>10s}  "
                f"{bic_s:>10s}  "
                f"{hqic_s:>10s}"
            )
            lines.append(row)

        lines.append(sep)
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.summary()


@dataclass
class _GrangerEntry:
    """Single Granger causality test entry (internal).

    Parameters
    ----------
    test_statistic : float
        Test statistic value (F or chi-squared).
    p_value : float
        p-value of the test.
    df : int or tuple
        Degrees of freedom. ``(numerator, denominator)`` for F-test,
        ``int`` for chi-squared test.
    caused : str
        Name of the variable being caused.
    causing : list of str
        Name(s) of the causing variable(s).
    """

    test_statistic: float
    p_value: float
    df: int | tuple
    caused: str
    causing: list


@dataclass
class GrangerCausalityResult:
    """Results of one or more Granger causality tests.

    Returned by :meth:`VARResult.granger_causality` (single test or
    all pairwise tests when called without arguments).
    Supports formatted table display via ``print()`` or ``.summary()``,
    and iteration over individual test entries.

    Parameters
    ----------
    tests : list of _GrangerEntry
        Individual test entries.
    kind : str
        Test type: ``"f"`` for F-test, ``"chi2"`` for chi-squared test.
    """

    tests: list
    kind: str = "f"

    def __str__(self) -> str:
        if not self.tests:
            return "No Granger causality test results."
        if len(self.tests) == 1:
            return _format_single(self.tests[0], self.kind)
        return _format_table(self.tests, self.kind)

    def summary(self) -> str:
        return str(self)

    def __len__(self) -> int:
        return len(self.tests)

    def __iter__(self):
        return iter(self.tests)

    def __getitem__(self, index):
        return self.tests[index]


def _format_single(entry, kind):
    """Format a single Granger test entry as a compact table."""
    stat_label = "F" if kind == "f" else "chi2"
    df_str = (
        f"{entry.df[0]}, {entry.df[1]}"
        if isinstance(entry.df, tuple)
        else str(entry.df)
    )
    sig = _sig_star(entry.p_value)
    cause_str = ", ".join(entry.causing)
    eq_w = max(len(entry.caused), 8) + 2
    ex_w = max(len(cause_str), 8) + 2

    top_rule = "=" * 60
    sep_rule = "-" * 60

    return "\n".join(
        [
            "Granger Causality Test",
            top_rule,
            f"{'Equation':<{eq_w}s} {'Excluded':<{ex_w}s} {stat_label:>10s} {'df':>10s} {'p-value':>10s}",
            sep_rule,
            f"{entry.caused:<{eq_w}s} {cause_str:<{ex_w}s} {entry.test_statistic:>10.4f} {df_str:>10s} {entry.p_value:>10.4f} {sig}",
            sep_rule,
        ]
    )


def _format_table(entries, kind):
    """Format multiple Granger test entries as a grouped table."""
    stat_label = "F" if kind == "f" else "chi2"

    max_caused = max(len(e.caused) for e in entries)
    max_causing = max(len(", ".join(e.causing)) for e in entries)
    eq_w = max(max_caused, 8) + 2
    ex_w = max(max_causing, 8) + 2

    total_w = eq_w + ex_w + 38
    top_rule = "=" * total_w
    sep_rule = "-" * total_w

    lines = [
        "Granger Causality Wald Tests",
        top_rule,
        f"{'Equation':<{eq_w}s} {'Excluded':<{ex_w}s} {stat_label:>10s} {'df':>8s} {'p-value':>10s}",
        sep_rule,
    ]

    prev_caused = None
    for e in entries:
        if prev_caused is not None and e.caused != prev_caused:
            lines.append(sep_rule)
        prev_caused = e.caused

        cause_str = ", ".join(e.causing)
        df_str = f"{e.df[0]}, {e.df[1]}" if isinstance(e.df, tuple) else str(e.df)
        sig = _sig_star(e.p_value)

        lines.append(
            f"{e.caused:<{eq_w}s} {cause_str:<{ex_w}s} "
            f"{e.test_statistic:>10.4f} {df_str:>8s} {e.p_value:>10.4f} {sig}"
        )

    lines.append(top_rule)
    lines.append("Significance codes:  ** p<0.01  * p<0.05  . p<0.10")
    return "\n".join(lines)


def _stata_fmt(val: float) -> str:
    """Format a value in Stata style: no leading zero, up to 6 decimals.

    Examples: ``1.0`` → ``"1"``, ``0.0`` → ``"0"``,
    ``0.01331`` → ``".01331"``, ``-0.01331`` → ``"-.01331"``.
    """
    if abs(val - 1.0) < 1e-12:
        return "1"
    if abs(val) < 1e-12:
        return "0"
    neg = val < 0
    s = f"{abs(val):.6f}".rstrip("0").rstrip(".")
    if abs(val) < 1:
        s = s.lstrip("0")
    if neg:
        s = "-" + s
    return s


def _sig_star(p_value: float) -> str:
    """Return significance star code for a p-value.

    ``**`` for p < 0.01, ``*`` for p < 0.05, ``.`` for p < 0.10,
    `` `` otherwise.
    """
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    if p_value < 0.10:
        return "."
    return " "


def _run_granger_all(result_obj, k, data_names, kind):
    """Run all pairwise Granger causality tests (shared by VAR and VECM).

    Parameters
    ----------
    result_obj : VARResult or VECMResult
        Fitted result object with a ``granger_causality(caused, causing, kind)``
        method returning ``GrangerCausalityResult``.
    k : int
        Number of endogenous variables.
    data_names : list of str
        Variable names.
    kind : str
        Test type: ``"f"`` for F-test, ``"chi2"`` for chi-squared.

    Returns
    -------
    GrangerCausalityResult
    """
    entries = []
    for eq_idx in range(k):
        other_idx = [j for j in range(k) if j != eq_idx]

        for causing_idx in other_idx:
            gc = result_obj.granger_causality(
                caused=eq_idx, causing=causing_idx, kind=kind
            )
            entries.append(gc[0])

        # Joint test: all other variables
        if len(other_idx) > 1:
            gc_all = result_obj.granger_causality(
                caused=eq_idx, causing=other_idx, kind=kind
            )
            entry = gc_all[0]
            entry.causing = ["ALL"]
            entries.append(entry)

    return GrangerCausalityResult(tests=entries, kind=kind)


@dataclass
class VARResult(BaseModelResult):
    """Result container for VAR model estimation.

    Inherits all fields from :class:`BaseModelResult` and adds VAR-specific
    impulse response, variance decomposition, and Granger causality methods.

    Parameters
    ----------
    _lags : int
        Number of lags used in estimation.
    _data_names : list of str
        Variable names for display.
    _k : int
        Number of endogenous variables.
    _var_result : object
        Raw statsmodels VARResultsWrapper, stored for internal delegation.
    _var_model : object
        Raw statsmodels VAR model, stored for forecast / IRF.
    """

    _lags: int = 1
    _data_names: list = None
    _k: int = 1
    _var_result: object = None
    _var_model: object = None
    _trend: str = "c"
    _irf_cache: dict | None = field(default=None, repr=False)

    def summary(self) -> str:
        """Return a formatted multi-equation parameter summary.

        Overrides BaseModelResult to display per-equation tables.
        """
        lines = [
            f"VAR({self._lags}) Model Estimation Result",
            "=" * 60,
            f"Variables  : {', '.join(self._data_names)}",
            f"Observations: {self.nobs}",
            f"Log-Likelihood: {self.log_likelihood:.4f}",
            f"AIC         : {self.aic:.4f}",
            f"BIC         : {self.bic:.4f}",
            "",
        ]

        if self._var_result is None:
            lines.append("(No fitted statsmodels result available)")
            return "\n".join(lines)

        params_flat = self.params
        se_flat = self.std_errors
        pv_flat = self.p_values

        for eq_idx in range(self._k):
            var_name = self._data_names[eq_idx]
            lines.append(f"Equation: {var_name}")
            lines.append("-" * 40)
            for name in sorted(params_flat):
                parts = name.split(".")
                eq_var = parts[-1]
                if eq_var != var_name:
                    continue
                # Strip redundant dependent-variable suffix: "L1.gnp_gr.gnp_gr" → "L1.gnp_gr"
                display = ".".join(parts[:-1])
                if len(parts) <= 1:
                    display = name
                val = params_flat[name]
                se = se_flat.get(name)
                pv = pv_flat.get(name)
                se_str = f"{se:.4f}" if se is not None else "N/A"
                pv_str = f"{pv:.4f}" if pv is not None else "N/A"
                lines.append(f"  {display:<30s} {val:>10.4f}  ({se_str})  p={pv_str}")
            for prefix in ("const", "trend", "trend2"):
                det_name = f"{prefix}.{var_name}"
                if det_name in params_flat:
                    val = params_flat[det_name]
                    se = se_flat.get(det_name)
                    pv = pv_flat.get(det_name)
                    se_str = f"{se:.4f}" if se is not None else "N/A"
                    pv_str = f"{pv:.4f}" if pv is not None else "N/A"
                    lines.append(
                        f"  {prefix:<30s} {val:>10.4f}  ({se_str})  p={pv_str}"
                    )
            lines.append("")
        return "\n".join(lines)

    def plot_fit(self, title=None):
        """Plot actual vs fitted for each variable in separate subplots.

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

        from Ts.TsPlots import plot_series

        k = self._k
        fig, axes = plt.subplots(k, 1, figsize=(10, 3 * k), squeeze=False)
        axes = axes[:, 0]

        data_aligned = self.data[-self.fitted_values.shape[0] :]

        for i in range(k):
            name = self._data_names[i]
            plot_data = {
                f"{name} (actual)": data_aligned[:, i],
                f"{name} (fitted)": self.fitted_values[:, i],
            }
            plot_series(
                plot_data,
                ax=axes[i],
                title=f"Variable: {name}",
                ytitle="Value",
            )

        if title is None:
            title = f"VAR({self._lags}): Actual vs Fitted"
        fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.tight_layout()
        return fig, axes

    def plot_diagnostics(self, title=None):
        """Plot diagnostic charts for each variable: residuals + ACF + PACF.

        Grid layout: k rows x 3 columns. Left: residuals; middle: ACF;
        right: PACF.

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

        from Ts.TsPlots import plot_series, plot_acf, plot_pacf

        k = self._k
        fig, axes = plt.subplots(k, 3, figsize=(14, 3 * k), squeeze=False)

        for i in range(k):
            name = self._data_names[i]

            plot_series(
                self.residuals[:, i],
                ax=axes[i, 0],
                title=f"{name} Residuals",
                ytitle="Residual",
                show_legend=False,
            )

            plot_acf(
                self.residuals[:, i],
                ax=axes[i, 1],
                title=f"{name} ACF",
            )

            plot_pacf(
                self.residuals[:, i],
                ax=axes[i, 2],
                title=f"{name} PACF",
            )

        if title is None:
            title = f"VAR({self._lags}): Diagnostic Plots"
        fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.tight_layout()
        return fig, axes

    def test_residuals(self, lags=10):
        """Run residual diagnostic tests for each variable.

        For each equation's residuals, runs the four standard tests:
        white noise, normality, Ljung-Box on squares, and Engle LM.

        Parameters
        ----------
        lags : int
            Number of lags for autocorrelation-based tests.

        Returns
        -------
        dict
            Mapping from variable name to :class:`ResidualTestResults`.
        """
        from Ts.TsTests import LjungBoxTest, EngleLMTest, NormalityTest
        from Ts.TsModels._base import ResidualTestResults

        results = {}
        for i in range(self._k):
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

    def irf(self, periods=10, orth=False, alpha=0.05):
        """Compute impulse response functions with confidence bands.

        Results are cached internally so that repeated calls with the same
        *(periods, orth, alpha)* combination share a single statsmodels IRF
        analysis computation.

        Parameters
        ----------
        periods : int
            Number of periods to compute IRF for.
        orth : bool
            If True, compute orthogonalized IRF via Cholesky decomposition.
        alpha : float
            Significance level for confidence bands (default 0.05 = 95%).

        Returns
        -------
        IRFResult
            Container with ``.values``, ``.lower``, ``.upper``,
            ``.summary()``, and ``.get()``.
        """
        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")

        cache_hit = (
            self._irf_cache is not None and self._irf_cache["periods"] == periods
        )

        if not cache_hit:
            irf_obj = self._var_result.irf(periods=periods)
            raw = np.asarray(irf_obj.irfs)
            orth_vals = np.asarray(irf_obj.orth_irfs)

            stderr_raw = np.asarray(irf_obj.stderr(orth=False))
            stderr_orth = np.asarray(irf_obj.stderr(orth=True))

            self._irf_cache = {
                "periods": periods,
                "raw": raw,
                "orth": orth_vals,
                "stderr_raw": stderr_raw,
                "stderr_orth": stderr_orth,
            }

        raw = self._irf_cache["raw"]
        orth_vals = self._irf_cache["orth"]
        stderr_raw = self._irf_cache["stderr_raw"]
        stderr_orth = self._irf_cache["stderr_orth"]

        z_crit = scipy_stats.norm.ppf(1.0 - alpha / 2.0)

        vals = orth_vals if orth else raw
        se = stderr_orth if orth else stderr_raw

        if se is not None:
            lower = vals - z_crit * se
            upper = vals + z_crit * se
        else:
            lower = None
            upper = None

        return IRFResult(
            values=vals.copy(),
            lower=lower,
            upper=upper,
            periods=periods,
            k=self._k,
            names=list(self._data_names),
            orth=orth,
            alpha=alpha,
            ci_method="analytic" if se is not None else None,
        )

    def fevd(self, periods=10, alpha=0.05, n_draws=200, seed=None):
        """Compute forecast error variance decomposition with confidence bands.

        Confidence intervals are computed via Monte Carlo sampling from the
        asymptotic distribution of VAR coefficients.

        Parameters
        ----------
        periods : int
            Number of periods.
        alpha : float
            Significance level for confidence bands (default 0.05 = 95%).
        n_draws : int
            Number of Monte Carlo draws (default 200).
        seed : int, optional
            Random seed for reproducibility.

        Returns
        -------
        FEVDResult
            Container with ``.values``, ``.lower``, ``.upper``,
            ``.summary()``, and ``.get()``.
        """
        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")

        # Point estimate from statsmodels
        fevd_obj = self._var_result.fevd(periods=periods)
        decomp = np.asarray(fevd_obj.decomp)
        values = np.transpose(decomp, (1, 0, 2)).copy()

        # Monte Carlo confidence intervals
        lower, upper = self._fevd_mc(
            periods=periods, alpha=alpha, n_draws=n_draws, seed=seed
        )

        return FEVDResult(
            values=values,
            lower=lower,
            upper=upper,
            periods=periods,
            k=self._k,
            names=list(self._data_names),
            method="mc",
            alpha=alpha,
            n_draws=n_draws,
        )

    def _fevd_mc(self, periods, alpha, n_draws, seed):
        """Monte Carlo FEVD confidence intervals.

        Draws VAR coefficients from their asymptotic normal distribution
        and computes FEVD for each draw to obtain empirical quantiles.

        Parameters
        ----------
        periods : int
        alpha : float
        n_draws : int
        seed : int or None

        Returns
        -------
        lower : np.ndarray shape (periods, k, k)
        upper : np.ndarray shape (periods, k, k)
        """
        k = self._k
        lags = self._lags
        fitted = self._var_result

        # Extract fitted parameter structure
        all_params = np.asarray(fitted.params)  # (n_regressors, k)
        resid = np.asarray(fitted.resid)
        sigma_u = np.cov(resid, rowvar=False)

        has_const = self._trend != "n"
        has_trend = self._trend in ("ct", "ctt")
        has_trend2 = self._trend == "ctt"
        n_det = int(has_const) + int(has_trend) + int(has_trend2)

        # Coefficient covariance
        beta_flat = all_params.ravel()  # C-order (row-major)
        cov_beta = np.asarray(fitted.cov_params())

        # Ensure cov_beta is positive definite for multivariate_normal
        eigvals = np.linalg.eigvalsh(cov_beta)
        min_ev = np.min(eigvals)
        if min_ev < 1e-15:
            cov_beta = cov_beta + np.eye(len(beta_flat)) * (1e-10 - min_ev)

        rng = np.random.default_rng(seed)

        # Cholesky factor of residual covariance
        P = np.linalg.cholesky(sigma_u)  # lower triangular

        fevd_draws = np.zeros((n_draws, periods, k, k))

        for d in range(n_draws):
            beta_d = rng.multivariate_normal(beta_flat, cov_beta)
            params_d = beta_d.reshape(all_params.shape)  # (n_regressors, k)

            # Extract A_1 ... A_p
            A_mats = []
            for lag_i in range(lags):
                start = n_det + lag_i * k
                A_lag = params_d[start : start + k, :].T  # (k, k)
                A_mats.append(A_lag)

            # MA coefficients via recursion
            ma_coefs = [np.eye(k)]  # Psi_0 = I
            for h in range(1, periods):
                psi_h = np.zeros((k, k))
                for j in range(1, min(h, lags) + 1):
                    psi_h += A_mats[j - 1] @ ma_coefs[h - j]
                ma_coefs.append(psi_h)

            # Orthogonalized MA coefficients
            orth_ma = [psi_s @ P for psi_s in ma_coefs]  # Theta_s

            # FEVD computation
            accum = np.zeros((k, k))
            for h in range(periods):
                accum += orth_ma[h] ** 2
                row_sums = accum.sum(axis=1, keepdims=True)
                fevd_draws[d, h] = accum / np.maximum(row_sums, 1e-20)

        lower = np.percentile(fevd_draws, alpha / 2.0 * 100.0, axis=0)
        upper = np.percentile(fevd_draws, (1.0 - alpha / 2.0) * 100.0, axis=0)
        return lower, upper

    def plot_irf(self, periods=10, orth=False, alpha=0.05, **kwargs):
        """Plot impulse response functions as a k x k subplot matrix.

        Uses TsPlots global style settings (Okabe-Ito palette,
        Times New Roman + Fangsong fonts). Confidence bands are drawn
        at the ``1 - alpha`` level.

        Parameters
        ----------
        periods : int
            Number of periods.
        orth : bool
            If True, use orthogonalized / structural IRF.
        alpha : float
            Significance level for confidence bands (default 0.05 = 95%).
        **kwargs
            Extra arguments forwarded to :meth:`irf` (e.g. ``n_draws``,
            ``seed`` for structural IRF).

        Returns
        -------
        fig : matplotlib.figure.Figure
        axes : numpy.ndarray of matplotlib.axes.Axes
        """
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator

        from Ts.TsPlots.style import (
            _ensure_fonts,
            DEFAULT_PALETTE,
            style_axes,
            TITLE_FONTSIZE,
            AXIS_LABEL_FONTSIZE,
            TICK_LABELSIZE,
        )

        _ensure_fonts()

        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")

        irf_result = self.irf(periods=periods, orth=orth, alpha=alpha, **kwargs)

        k = self._k
        fig, axes = plt.subplots(k, k, figsize=(3 * k, 3 * k), squeeze=False)

        for i in range(k):
            color = DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)]
            for j in range(k):
                ax = axes[i, j]
                ax.plot(
                    range(periods + 1),
                    irf_result.values[:, i, j],
                    color=color,
                    linewidth=1.2,
                )
                ax.axhline(0, color="#999999", linewidth=0.5, linestyle="--")

                if irf_result.lower is not None:
                    ax.fill_between(
                        range(periods + 1),
                        irf_result.lower[:, i, j],
                        irf_result.upper[:, i, j],
                        color=color,
                        alpha=0.15,
                        linewidth=0,
                    )

                ax.xaxis.set_major_locator(MaxNLocator(integer=True))
                if i == k - 1:
                    ax.set_xlabel(
                        f"Shock: {irf_result.names[j]}",
                        fontsize=AXIS_LABEL_FONTSIZE,
                    )
                if j == 0:
                    ax.set_ylabel(
                        f"Resp: {irf_result.names[i]}",
                        fontsize=AXIS_LABEL_FONTSIZE,
                    )

                ax.tick_params(labelsize=TICK_LABELSIZE)
                style_axes(ax)

        irf_type = irf_result.label or ("Orthogonalized IRF" if orth else "IRF")
        ci_label = f"{int((1 - alpha) * 100)}%"
        model_label = self.model_type
        fig.suptitle(
            f"{model_label}({self._lags}): {irf_type} ({periods} periods, {ci_label} CI)",
            fontsize=TITLE_FONTSIZE,
            fontweight="bold",
        )
        fig.tight_layout(pad=1.5)
        return fig, axes

    def granger_causality(self, caused=None, causing=None, kind="f"):
        """Test Granger causality.

        Tests whether lagged values of ``causing`` help predict ``caused``.

        When both ``caused`` and ``causing`` are ``None`` (default), runs
        all pairwise tests: for a :math:`k`-variable VAR this covers
        :math:`k \\times (k - 1)` individual tests plus one joint ``ALL``
        test per equation (equivalent to Stata ``vargranger``).

        Parameters
        ----------
        caused : int or str, optional
            Index or name of the variable being caused. Required when
            ``causing`` is specified.
        causing : int, str, or list, optional
            Index/name or list of indices/names of the causing variable(s).
            Required when ``caused`` is specified.
        kind : str
            Test type: ``"f"`` for F-test, ``"chi2"`` for chi-squared.

        Returns
        -------
        GrangerCausalityResult
            Result with formatted ``__str__``. Iterate or index ``[0]``
            to access individual ``.test_statistic``, ``.p_value``, etc.

        Raises
        ------
        ValueError
            If only one of ``caused`` / ``causing`` is specified.
        """
        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")

        # Dispatch: all-pairs mode vs single-test mode
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

        # statsmodels uses "wald" for chi-squared test
        sm_kind = "wald" if kind == "chi2" else kind
        test_result = self._var_result.test_causality(
            caused=caused, causing=causing_idx, kind=sm_kind
        )
        df_val = test_result.df
        if isinstance(df_val, tuple):
            df_val = (int(df_val[0]), int(df_val[1]))
        else:
            df_val = int(df_val)

        entry = _GrangerEntry(
            test_statistic=float(test_result.test_statistic),
            p_value=float(test_result.pvalue),
            df=df_val,
            caused=self._data_names[caused],
            causing=[self._data_names[i] for i in causing_idx],
        )
        return GrangerCausalityResult(tests=[entry], kind=kind)

    def _granger_causality_all(self, kind="f"):
        """Run all pairwise Granger causality tests (internal)."""
        return _run_granger_all(self, self._k, self._data_names, kind)

    @property
    def is_stable(self):
        """Check if the VAR process is stable.

        Stability requires all inverse roots of the characteristic polynomial
        to lie inside the unit circle (modulus < 1). Delegates to the
        underlying statsmodels result.

        Returns
        -------
        bool
            True if the VAR is covariance-stationary.
        """
        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")
        return bool(self._var_result.is_stable())

    def plot_roots(self, title=None):
        """Plot inverse roots of the VAR characteristic polynomial on the
        complex unit circle.

        For a stable (covariance-stationary) VAR, all inverse roots must lie
        inside the unit circle (modulus < 1).

        Uses TsPlots global style settings.

        Parameters
        ----------
        title : str, optional
            Chart title. If None, a default title with stability verdict
            is generated.

        Returns
        -------
        fig : matplotlib.figure.Figure
        ax : matplotlib.axes.Axes
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

        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")

        # statsmodels .roots are the characteristic polynomial roots.
        # For stability: |root| > 1 (outside the unit circle).
        # We plot inverse roots (1/root): for stability, |1/root| < 1
        # (inside the unit circle). This matches the standard VAR
        # stability visualization convention (EViews, Stata, etc.).
        raw_roots = np.asarray(self._var_result.roots)
        inv_roots = 1.0 / raw_roots

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

        # Scale to unit circle + small margin (inverse roots are all < 1)
        ax.set_xlim(-1.3, 1.3)
        ax.set_ylim(-1.3, 1.3)

        ax.set_xlabel("Real", fontsize=AXIS_LABEL_FONTSIZE)
        ax.set_ylabel("Imaginary", fontsize=AXIS_LABEL_FONTSIZE)
        ax.tick_params(labelsize=TICK_LABELSIZE)

        if title is None:
            status = "Stable" if self.is_stable else "NOT stable"
            title = f"VAR({self._lags}): Inverse Roots ({status})"
        ax.set_title(title, fontsize=TITLE_FONTSIZE, fontweight="bold")

        fig.tight_layout(pad=1.5)
        return fig, ax

    def predict(self, start=0, end=None, alpha=0.05):
        """Return in-sample predictions and forecasts beyond the sample.

        Parameters
        ----------
        start : int
            Start index (0-based).
        end : int, optional
            End index. If > nobs-1, performs out-of-sample forecast.
            Default: nobs-1.
        alpha : float
            Significance level for confidence intervals (default 0.05).

        Returns
        -------
        PredictResult
        """
        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")
        nobs = self.nobs
        k = self._k
        window = _resolve_prediction_window(nobs, start, end)
        alpha = _validate_prediction_alpha(alpha)
        start, end = window.start, window.end
        mean = np.full((window.size, k), np.nan)
        lower = None
        upper = None
        is_oos = np.zeros(window.size, dtype=bool)

        if window.has_forecast:
            # In-sample + out-of-sample forecast
            n_in = window.in_sample_size
            if n_in > 0:
                mean[:n_in] = self.fitted_values[start:nobs]

            z_val = scipy_stats.norm.ppf(1.0 - alpha / 2.0)
            fc_mean, fc_lower, fc_upper = self._forecast(
                steps=window.forecast_steps,
                z_val=z_val,
            )
            forecast_slice = slice(window.forecast_skip, None)
            mean[n_in:] = fc_mean[forecast_slice]
            lower = np.full((window.size, k), np.nan)
            upper = np.full((window.size, k), np.nan)
            lower[n_in:] = fc_lower[forecast_slice]
            upper[n_in:] = fc_upper[forecast_slice]
            is_oos[n_in:] = True

        else:
            # Pure in-sample
            mean = self.fitted_values[start : end + 1].copy()

        return PredictResult(
            mean=mean,
            lower=lower,
            upper=upper,
            is_oos=is_oos,
            _full_data=self.data,
            _full_fitted=self.fitted_values,
            _start=start,
        )

    def _forecast(self, steps, z_val=1.96):
        """Internal out-of-sample forecast with confidence intervals.

        Parameters
        ----------
        steps : int
            Number of steps ahead.
        z_val : float
            Critical value for confidence intervals.

        Returns
        -------
        mean : np.ndarray (steps, k)
        lower : np.ndarray (steps, k)
        upper : np.ndarray (steps, k)
        """
        fc = self._var_result.forecast(self.data[-self._lags :], steps=steps)
        mean = np.asarray(fc)
        fc_lower, fc_upper = self._forecast_ci(mean=mean, steps=steps, z_val=z_val)
        return mean, fc_lower, fc_upper

    def _forecast_ci(self, mean, steps, z_val=1.96):
        """Compute confidence intervals for VAR forecasts.

        Parameters
        ----------
        mean : np.ndarray (steps, k)
            Point forecasts.
        steps : int
        z_val : float

        Returns
        -------
        lower : np.ndarray (steps, k)
        upper : np.ndarray (steps, k)
        """
        resid_cov = np.cov(self.residuals, rowvar=False)
        ma_coefs = self._var_result.ma_rep(maxn=steps)

        lower = np.empty_like(mean)
        upper = np.empty_like(mean)
        for h in range(steps):
            accum = np.zeros((self._k, self._k))
            for s in range(h + 1):
                phi_s = np.asarray(ma_coefs[s])
                accum += phi_s @ resid_cov @ phi_s.T
            se = np.sqrt(np.diag(accum))
            lower[h] = mean[h] - z_val * se
            upper[h] = mean[h] + z_val * se
        return lower, upper

    def long_run_equilibrium(self):
        """Return the unconditional mean vector (long-run equilibrium) of the
        estimated VAR process.

        For a stable VAR(p) with constant term:

        .. math::

            \\boldsymbol{\\mu}
            = (\\mathbf{I} - \\mathbf{A}_1 - \\dots - \\mathbf{A}_p)^{-1}
            \\mathbf{c}

        Returns ``None`` when:

        - The VAR is not stable (``is_stable`` is ``False``).
        - ``trend`` includes a time component (``"ct"``, ``"ctt"``) —
          trend-stationary series have no constant equilibrium.

        Returns
        -------
        np.ndarray or None
            Unconditional mean vector of shape ``(k,)``, or ``None``.
        """
        if self._var_result is None:
            raise RuntimeError("No fitted VAR result available")

        if not self.is_stable:
            return None

        # Trend-stationary — no constant long-run equilibrium
        if self._trend in ("ct", "ctt"):
            return None

        k = self._k
        all_params = np.asarray(self._var_result.params)  # (n_coefs, k)

        has_const = self._trend != "n"
        offset = 1 if has_const else 0

        c_vec = all_params[0, :] if has_const else np.zeros(k)

        # Sum A_1 + ... + A_p
        sum_A = np.zeros((k, k))
        for lag in range(self._lags):
            start = offset + lag * k
            A_lag = all_params[start : start + k, :].T  # (k, k)
            sum_A += A_lag

        # μ = (I - ΣA)⁻¹ · c
        try:
            inv_mat = np.linalg.inv(np.eye(k) - sum_A)
        except np.linalg.LinAlgError:
            return None

        return inv_mat @ c_vec


class VAR(BaseModel):
    """Vector Autoregression (VAR) model estimation.

    Parameters
    ----------
    data : array-like
        Time series data, shape (nobs, k) or a pandas DataFrame.
    lags : int
        Number of lags (>= 1).
    trend : str
        Trend specification: ``"c"`` (constant), ``"ct"`` (constant + trend),
        ``"ctt"`` (constant + quadratic trend), ``"n"`` (none).
        Default ``"c"``.
    cols : list of str, optional
        Column names to include in the model. When *data* is a DataFrame,
        only the named columns are extracted; when *data* is an ndarray,
        *cols* provides display names. If None with a DataFrame, all columns
        are used and names are taken from the DataFrame; for an ndarray
        names are auto-generated as ``"y0"``, ``"y1"``, ...
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
        lags=1,
        trend="c",
        cols=None,
        dates=None,
        missing="raise",
    ):
        model_dates = _normalise_model_dates(data, dates, len(data))
        # Column selection for DataFrame inputs
        if hasattr(data, "columns"):
            if cols is not None:
                data = data[cols]
            else:
                cols = list(data.columns)

        y = np.asarray(data, dtype=float)
        if y.ndim != 2:
            raise ValueError(f"data must be 2-D (nobs, k), got shape {y.shape}")

        # Resolve variable names
        if cols is not None:
            if len(cols) != y.shape[1]:
                raise ValueError(
                    f"cols length ({len(cols)}) must match "
                    f"number of variables ({y.shape[1]})"
                )
            data_names = list(cols)
        else:
            data_names = [f"y{i}" for i in range(y.shape[1])]

        finite_rows = np.all(np.isfinite(y), axis=1)
        dropped_positions = _resolve_missing_rows(finite_rows, missing)
        if missing == "drop":
            if model_dates is not None:
                model_dates = model_dates[finite_rows].copy()
            y = y[finite_rows]
        else:
            y = y.copy()

        if lags < 1:
            raise ValueError(f"lags must be >= 1, got {lags}")
        if trend not in ("c", "ct", "ctt", "n"):
            raise ValueError(
                f"trend must be one of 'c', 'ct', 'ctt', 'n', got {trend!r}"
            )
        min_obs = lags + 10
        if y.shape[0] < min_obs:
            raise ValueError(
                f"Need at least {min_obs} observations "
                f"({lags} lags + 10), got {y.shape[0]}"
            )

        self.dates = model_dates
        self.data = y
        self.missing = missing
        self.dropped_positions = dropped_positions
        self.lags = lags
        self.trend = trend
        self.data_names = data_names

    @staticmethod
    def select_order(
        data,
        max_lags,
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
        criterion : str
            Criterion: ``"aic"``, ``"bic"``, ``"hqic"``, ``"fpe"``.
        cols : list of str, optional
            Column names to include. When *data* is a DataFrame, only the
            named columns are extracted; when *data* is an ndarray, *cols*
            provides display names. If None with a DataFrame, all numeric
            columns are used.

        Returns
        -------
        VAROrderResult
            Result object with ``summary()`` for formatted table display.
        """
        from statsmodels.tsa.vector_ar.var_model import VAR as _SM_VAR

        # Column selection for DataFrame inputs (consistent with VAR.__init__)
        if hasattr(data, "columns") and cols is not None:
            data = data[cols]

        y = np.asarray(data, dtype=float)
        if y.ndim != 2:
            raise ValueError(f"data must be 2-D (nobs, k), got shape {y.shape}")
        finite_rows = np.all(np.isfinite(y), axis=1)
        dropped_positions = _resolve_missing_rows(finite_rows, missing)
        y = y[finite_rows] if missing == "drop" else y.copy()

        sm_model = _SM_VAR(y)
        result = sm_model.select_order(max_lags)

        valid_criteria = {"aic", "bic", "hqic", "fpe"}
        if criterion not in valid_criteria:
            raise ValueError(
                f"criterion must be one of {sorted(valid_criteria)}, got {criterion!r}"
            )

        # Collect all criteria values (ics values are lists, indexed by lag)
        criteria_table = {}
        for crit_name in ["aic", "bic", "hqic", "fpe"]:
            ics_list = result.ics.get(crit_name, [])
            criteria_table[crit_name] = {
                lag: float(ics_list[lag])
                for lag in range(min(len(ics_list), max_lags + 1))
            }

        # Extract LL for each lag by fitting models 0..max_lags
        ll_values = {}
        lr_values = {}
        df_values = {}
        p_values = {}
        prev_ll = None
        prev_n_params = None
        k = y.shape[1]
        for lag in range(max_lags + 1):
            if lag == 0:
                # VAR(0): intercept only regression per equation
                import statsmodels.api as sm_lm

                ll_total = 0.0
                n_params_total = 0
                for eq in range(k):
                    x = np.ones((len(y), 1))
                    lm = sm_lm.OLS(y[:, eq], x).fit()
                    ll_total += lm.llf
                    n_params_total += 1
                ll_values[0] = ll_total
                prev_ll = ll_total
                prev_n_params = n_params_total
                lr_values[0] = None
                df_values[0] = None
                p_values[0] = None
            else:
                fitted = sm_model.fit(maxlags=lag, trend="c", ic=None)
                ll = float(fitted.llf)
                ll_values[lag] = ll
                n_params = k * (1 + k * lag)  # const + k lags per eq * k equations
                if prev_ll is not None:
                    lr_stat = 2.0 * (ll - prev_ll)
                    df_diff = n_params - prev_n_params
                    p_val = 1.0 - scipy_stats.chi2.cdf(lr_stat, df_diff)
                    lr_values[lag] = lr_stat
                    df_values[lag] = df_diff
                    p_values[lag] = p_val
                else:
                    lr_values[lag] = None
                    df_values[lag] = None
                    p_values[lag] = None
                prev_ll = ll
                prev_n_params = n_params

        criteria_table["ll"] = ll_values
        criteria_table["lr"] = lr_values
        criteria_table["df"] = df_values
        criteria_table["p"] = p_values

        # Selected lag from the chosen criterion
        crit_vals = criteria_table[criterion]
        best_lag = 1
        best_val = float("inf")
        for lag in range(1, max_lags + 1):
            val = float(crit_vals[lag])
            if val < best_val:
                best_val = val
                best_lag = lag

        # Resolve endogenous names
        if hasattr(data, "columns"):
            endogenous = list(data.columns)
        else:
            endogenous = [f"y{i}" for i in range(k)]

        return VAROrderResult(
            selected_lag=best_lag,
            criterion=criterion,
            criteria_table=criteria_table,
            endogenous=endogenous,
            max_lags=max_lags,
            nobs=len(y),
            dropped_positions=dropped_positions,
        )

    def fit(self):
        """Estimate the VAR model via equation-by-equation OLS.

        Returns
        -------
        VARResult
        """
        from statsmodels.tsa.vector_ar.var_model import VAR as _SM_VAR

        sm_var = _SM_VAR(self.data)
        fitted = sm_var.fit(
            maxlags=self.lags,
            trend=self.trend,
            ic=None,
        )

        k = self.data.shape[1]
        names = self._build_param_names(k, self.lags)
        param_arr = np.asarray(fitted.params).ravel()
        stderr_arr = np.asarray(fitted.stderr).ravel()
        pval_arr = np.asarray(fitted.pvalues).ravel()

        params = {}
        std_errors = {}
        p_values = {}
        for idx, name in enumerate(names):
            if idx < len(param_arr):
                params[name] = float(param_arr[idx])
            if idx < len(stderr_arr):
                std_errors[name] = float(stderr_arr[idx])
            if idx < len(pval_arr):
                p_values[name] = float(pval_arr[idx])

        resid = np.asarray(fitted.resid)
        fitted_vals = np.asarray(fitted.fittedvalues)

        result = VARResult(
            model_type="VAR",
            params=params,
            std_errors=std_errors,
            p_values=p_values,
            aic=float(fitted.aic),
            bic=float(fitted.bic),
            log_likelihood=float(fitted.llf),
            residuals=resid,
            fitted_values=fitted_vals,
            nobs=int(fitted.nobs),
            data=self.data,
            _lags=self.lags,
            _data_names=self.data_names,
            _k=k,
            _var_result=fitted,
            _var_model=sm_var,
            _trend=self.trend,
        )

        self.result_ = result
        return result

    def _build_param_names(self, k, lags):
        """Build parameter names list matching statsmodels VAR flat layout.

        statsmodels VAR stores ``params`` as a (num_coefs, k) matrix:
        each row is a regressor, each column is an equation.

        Ravel order (row-major): for each regressor, iterate through equations.

        Regressor order: const (if trend), trend (if ct/ctt), trend2 (if ctt),
        then L1.y0, L1.y1, ..., L2.y0, L2.y1, ... for each lag.
        """
        names = []
        regressor_names = []
        if self.trend in ("c", "ct", "ctt"):
            regressor_names.append("const")
        if self.trend in ("ct", "ctt"):
            regressor_names.append("trend")
        if self.trend == "ctt":
            regressor_names.append("trend2")
        for lag in range(1, lags + 1):
            for vj in range(k):
                regressor_names.append(f"L{lag}.{self.data_names[vj]}")  # noqa: PERF401 - explicit ordering

        for reg_name in regressor_names:
            for eq_idx in range(k):
                eq_var = self.data_names[eq_idx]
                names.append(f"{reg_name}.{eq_var}")
        return names
