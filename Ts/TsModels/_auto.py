"""Auto-estimation for SARIMA and GARCH models.

Provides automatic optimal parameter selection via grid search over
user-specified parameter ranges and evaluation criteria.

Classes
-------
_BaseAutoModel
    Shared grid-search logic for AutoSARIMA and AutoGARCH.
AutoModelResult
    Result container for auto-estimation (inherits BaseModelResult).
AutoSARIMA
    Auto SARIMA model selection via grid search.
AutoGARCH
    Auto GARCH model selection via grid search.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from Ts.TsUtils._validation import _resolve_missing_rows

from Ts.TsModels._base import (
    _GARCH_M_FORMS,
    _VOL_TYPES,
    BaseModel,
    BaseModelResult,
    _normalise_model_dates,
)

_SUPPORTED_CRITERIA = frozenset({"aic", "bic", "hqic", "aicc"})


def _get_criterion_value(result: BaseModelResult, criterion: str) -> float:
    """Extract or compute the value of an information criterion.

    Reads ``aic`` / ``bic`` directly from *result*; computes ``hqic``
    and ``aicc`` from log-likelihood, parameter count, and sample size.

    Parameters
    ----------
    result : BaseModelResult
        Fitted model result.
    criterion : str
        One of ``"aic"``, ``"bic"``, ``"hqic"``, ``"aicc"``.

    Returns
    -------
    float
        Criterion value (lower is better).
    """
    if criterion == "aic":
        return float(result.aic)
    if criterion == "bic":
        return float(result.bic)

    k = len(result.params)
    n = result.nobs
    llf = result.log_likelihood

    if criterion == "hqic":
        import math

        return -2.0 * llf + 2.0 * k * math.log(max(1.0001, math.log(n)))

    if criterion == "aicc":
        correction = 2.0 * k * (k + 1.0) / max(1.0, n - k - 1.0)
        return float(result.aic) + correction

    raise ValueError(
        f"Unknown criterion: {criterion!r}. Supported: {sorted(_SUPPORTED_CRITERIA)}"
    )


@dataclass
class AutoModelResult(BaseModelResult):
    """Result container for automatic model selection.

    Inherits all estimation fields from :class:`BaseModelResult` (copied
    from the best model) and adds selection metadata.

    Use :meth:`from_search` to construct from a search result.

    Parameters
    ----------
    best_result : BaseModelResult
        The best model's full result object.
    best_order : tuple
        Optimal parameter combination (e.g. ``(1, 0, 0)`` for SARIMA or
        ``(p, o, q)`` for GARCH / GJR-GARCH).
    candidate_results : list
        All successfully fitted :class:`BaseModelResult` objects.
    candidate_orders : list
        All parameter combinations that were attempted and succeeded.
    criterion_values : list
        Criterion value for each successfully fitted model.
    selection_criterion : str
        Criterion used for selection (``"aic"``, ``"bic"``, ``"hqic"``,
        ``"aicc"``).
    search_method : str
        Search strategy (``"grid"``).
    n_attempted : int, optional
        Number of order combinations attempted, including failed fits.
    best_seasonal_order : tuple, optional
        Seasonal order selected by :class:`AutoSARIMA`, if seasonal search
        was enabled.
    candidate_seasonal_orders : list, optional
        Seasonal orders corresponding to successful AutoSARIMA candidates.
    search_messages : list of str, optional
        Warnings and failed-fit messages collected during the search.
    """

    best_result: BaseModelResult = field(default=None, repr=False)
    best_order: tuple = field(default=())
    candidate_results: list = field(default_factory=list, repr=False)
    candidate_orders: list = field(default_factory=list, repr=False)
    criterion_values: list = field(default_factory=list, repr=False)
    selection_criterion: str = ""
    search_method: str = ""
    n_attempted: int | None = None
    best_seasonal_order: tuple | None = None
    candidate_seasonal_orders: list = field(default_factory=list, repr=False)
    search_messages: list[str] = field(default_factory=list, repr=False)

    @classmethod
    def from_search(
        cls,
        best_result: BaseModelResult,
        best_order: tuple,
        candidate_results: list,
        candidate_orders: list,
        criterion_values: list,
        selection_criterion: str,
        search_method: str,
        n_attempted: int | None = None,
        best_seasonal_order: tuple | None = None,
        candidate_seasonal_orders: list | None = None,
        search_messages: list[str] | None = None,
    ) -> AutoModelResult:
        """Construct from a search loop outcome.

        Copies :class:`BaseModelResult` fields from *best_result* and
        stores selection metadata in the additional fields.

        Parameters
        ----------
        best_result : BaseModelResult
            Result of the best model found.
        best_order : tuple
            Parameter combination of the best model.
        candidate_results : list of BaseModelResult
            All successfully fitted results.
        candidate_orders : list of tuple
            Corresponding parameter combinations.
        criterion_values : list of float
            Criterion value for each candidate.
        selection_criterion : str
            Criterion name.
        search_method : str
            Search strategy name.

        Returns
        -------
        AutoModelResult
        """
        return cls(
            model_type=best_result.model_type,
            params=best_result.params,
            std_errors=best_result.std_errors,
            p_values=best_result.p_values,
            aic=best_result.aic,
            bic=best_result.bic,
            log_likelihood=best_result.log_likelihood,
            residuals=best_result.residuals,
            fitted_values=best_result.fitted_values,
            nobs=best_result.nobs,
            data=best_result.data,
            best_result=best_result,
            best_order=best_order,
            candidate_results=candidate_results,
            candidate_orders=candidate_orders,
            criterion_values=criterion_values,
            selection_criterion=selection_criterion,
            search_method=search_method,
            n_attempted=n_attempted,
            best_seasonal_order=best_seasonal_order,
            candidate_seasonal_orders=(
                [] if candidate_seasonal_orders is None else candidate_seasonal_orders
            ),
            search_messages=[] if search_messages is None else search_messages,
        )

    def summary(self) -> str:
        """Return a formatted summary with selection header.

        Prepends auto-selection metadata (best order, criterion, success
        count) before the best model's full parameter table.
        """
        n_ok = len(self.candidate_results)
        n_total = n_ok if self.n_attempted is None else self.n_attempted

        lines = [
            f"Auto {self.model_type} Model Selection Result",
            "=" * 60,
            f"Search Method      : {self.search_method}",
            f"Selection Criterion: {self.selection_criterion.upper()}",
            f"Best Order         : {self.best_order}",
            f"Models Evaluated   : {n_ok}/{n_total} successful",
            f"Search Diagnostics : {len(self.search_messages)}",
            f"Best {self.selection_criterion.upper():>6s}        : {_get_criterion_value(self, self.selection_criterion):.4f}",
            "",
            "Best Model Details:",
            "-" * 60,
        ]
        if self.best_seasonal_order is not None:
            lines.insert(5, f"Best Seasonal Order: {self.best_seasonal_order}")

        # Rebuild base summary from fields directly to get the clean table
        base_lines = [
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
            base_lines.append(f"  {name:<20s} {val:>10.4f}  ({se_str})  p={pv_str}")

        return "\n".join(lines + base_lines)

    def predict(self, **kwargs):
        """Unified prediction: delegates to :meth:`best_result.predict`.

        Parameters
        ----------
        **kwargs
            Forwarded to the best model's ``predict()`` method.

        Returns
        -------
        PredictResult
        """
        if self.best_result is None:
            raise RuntimeError("No best_result available")
        return self.best_result.predict(**kwargs)

    def long_run_equilibrium(self):
        """Return the long-run equilibrium of the best model.

        Delegates to :meth:`BaseModelResult.long_run_equilibrium` of the
        wrapped best result.

        Returns
        -------
        float or np.ndarray or None
        """
        if self.best_result is not None:
            return self.best_result.long_run_equilibrium()
        return None


_SUPPORTED_METHODS = frozenset({"grid"})


class _BaseAutoModel(BaseModel):
    """Shared grid-search logic for AutoSARIMA and AutoGARCH."""

    def _validate_params(self, data, criterion, method):
        """Common validation shared by subclasses.

        Parameters
        ----------
        data : array-like
            Time series data.
        criterion : str
            Selection criterion.
        method : str
            Search strategy.

        Returns
        -------
        np.ndarray
            Cleaned 1-D data array.
        """
        y = np.asarray(data, dtype=float).ravel()
        if not np.all(np.isfinite(y)):
            raise ValueError("data must contain only finite values")
        if len(y) < 10:
            raise ValueError(f"Need at least 10 observations, got {len(y)}")
        if criterion not in _SUPPORTED_CRITERIA:
            raise ValueError(
                f"criterion must be one of {sorted(_SUPPORTED_CRITERIA)}, "
                f"got {criterion!r}"
            )
        if method not in _SUPPORTED_METHODS:
            raise ValueError(
                f"method must be one of {sorted(_SUPPORTED_METHODS)}, got {method!r}"
            )
        return y

    def _run_grid_search(self, y, orders, build_model, criterion):
        """Common grid search loop.

        Parameters
        ----------
        y : np.ndarray
            1D array of data.
        orders : iterable of tuple
            Parameter combinations to try.
        build_model : callable(tuple) -> BaseModel
            Factory that creates a model from an order tuple.
        criterion : str
            Selection criterion.

        Returns
        -------
        tuple
            (best_result, best_order, candidate_results, candidate_orders,
            n_attempted, search_messages)
        """
        import warnings

        best_result = None
        best_order = None
        best_value = float("inf")
        candidate_results = []
        candidate_orders = []

        n_attempted = 0
        search_messages = []
        for order in orders:
            n_attempted += 1
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                try:
                    model = build_model(order)
                    result = model.fit()
                    value = _get_criterion_value(result, criterion)
                except Exception as error:
                    search_messages.append(f"{order}: {type(error).__name__}: {error}")
                    continue
            search_messages.extend(
                f"{order}: {warning.category.__name__}: {warning.message}"
                for warning in caught_warnings
            )
            candidate_results.append(result)
            candidate_orders.append(order)
            if value < best_value:
                best_value = value
                best_result = result
                best_order = order

        if best_result is None:
            raise RuntimeError("No model converged during grid search")

        return (
            best_result,
            best_order,
            candidate_results,
            candidate_orders,
            n_attempted,
            search_messages,
        )


class AutoSARIMA(_BaseAutoModel):
    """Auto SARIMA model selection via grid search.

    Searches over a user-specified range of ``(p, d, q)`` and optional
    ``(P, D, Q, s)`` combinations, selecting the order that minimises
    the chosen information criterion.

    Parameters
    ----------
    data : array-like
        Time series data (1-D).
    p : tuple[int, int]
        AR order range ``(min, max)``. Default ``(0, 3)``.
    d : tuple[int, int]
        Differencing order range ``(min, max)``. Default ``(0, 1)``.
    q : tuple[int, int]
        MA order range ``(min, max)``. Default ``(0, 3)``.
    P : tuple[int, int]
        Seasonal AR range. Default ``(0, 1)``.
    D : tuple[int, int]
        Seasonal differencing range. Default ``(0, 1)``.
    Q : tuple[int, int]
        Seasonal MA range. Default ``(0, 1)``.
    s : int
        Seasonal period (0 = no seasonality). Default ``0``.
    trend : str
        Trend: ``"n"``, ``"c"``, ``"t"``, ``"ct"``. Default ``"c"``.
    criterion : str
        ``"aic"``, ``"bic"``, ``"hqic"``, or ``"aicc"``.
    method : str
        Search strategy. Currently only ``"grid"``.
    missing : {"raise", "drop"}
        Non-finite input policy. ``"drop"`` records removed zero-based rows
        in :attr:`dropped_positions`. Default ``"raise"``.
    dates : datetime-like sequence, optional
        Strict sample dates. A Series DatetimeIndex is inferred automatically.
        Array inputs may provide dates explicitly.
    """

    def __init__(
        self,
        data,
        p=(0, 3),
        d=(0, 1),
        q=(0, 3),
        P=(0, 1),
        D=(0, 1),
        Q=(0, 1),
        s=0,
        trend="c",
        criterion="aic",
        method="grid",
        dates=None,
        missing="raise",
    ):
        raw_data = np.asarray(data, dtype=float).ravel()
        finite_rows = np.isfinite(raw_data)
        model_dates = _normalise_model_dates(data, dates, len(raw_data))
        dropped_positions = _resolve_missing_rows(
            finite_rows,
            missing,
        )
        data = raw_data[finite_rows] if missing == "drop" else raw_data.copy()
        self.missing = missing
        if missing == "drop" and model_dates is not None:
            model_dates = model_dates[finite_rows].copy()
        self.dropped_positions = dropped_positions

        self.data = self._validate_params(data, criterion, method)
        self.criterion = criterion
        self.dates = model_dates
        self.method = method

        self.p_range = self._validate_range(p, "p")
        self.d_range = self._validate_range(d, "d")
        self.q_range = self._validate_range(q, "q")
        self.P_range = self._validate_range(P, "P")
        self.D_range = self._validate_range(D, "D")
        self.Q_range = self._validate_range(Q, "Q")
        self.s = s
        self.trend = trend

    @staticmethod
    def _validate_range(rng, name):
        """Validate and convert a (min, max) range tuple."""
        if not isinstance(rng, (tuple, list)) or len(rng) != 2:
            raise ValueError(f"{name} must be a (min, max) tuple, got {rng}")
        lo, hi = int(rng[0]), int(rng[1])
        if lo < 0 or hi < 0:
            raise ValueError(f"{name} range values must be >= 0, got ({lo}, {hi})")
        if lo > hi:
            raise ValueError(f"{name}: min ({lo}) must be <= max ({hi})")
        return (lo, hi)

    def fit(self):
        """Run grid search and return the best model.

        Returns
        -------
        AutoModelResult
        """
        import itertools

        from Ts.TsModels._sarima import SARIMA

        p_lo, p_hi = self.p_range
        d_lo, d_hi = self.d_range
        q_lo, q_hi = self.q_range
        P_lo, P_hi = self.P_range
        D_lo, D_hi = self.D_range
        Q_lo, Q_hi = self.Q_range

        nonseasonal = itertools.product(
            range(p_lo, p_hi + 1),
            range(d_lo, d_hi + 1),
            range(q_lo, q_hi + 1),
        )

        if self.s > 0:
            seasonal = itertools.product(
                range(P_lo, P_hi + 1),
                range(D_lo, D_hi + 1),
                range(Q_lo, Q_hi + 1),
                [self.s],
            )
        else:
            seasonal = ((0, 0, 0, 0),)

        # Each order is a (nonseasonal, seasonal) pair
        orders = itertools.product(nonseasonal, seasonal)

        def build_model(order_tuple):
            ns_order, s_order = order_tuple
            return SARIMA(
                self.data,
                order=ns_order,
                seasonal_order=s_order,
                trend=self.trend,
                dates=self.dates,
            )

        (
            best_result,
            best_order_pair,
            candidate_results,
            candidate_orders,
            n_attempted,
            search_messages,
        ) = self._run_grid_search(self.data, orders, build_model, self.criterion)

        criterion_values = [
            _get_criterion_value(r, self.criterion) for r in candidate_results
        ]

        # Extract nonseasonal order for reporting
        best_order = best_order_pair[0]
        flat_orders = [o[0] for o in candidate_orders]
        seasonal_orders = [o[1] for o in candidate_orders]

        auto_result = AutoModelResult.from_search(
            best_result=best_result,
            best_order=best_order,
            candidate_results=candidate_results,
            candidate_orders=flat_orders,
            criterion_values=criterion_values,
            selection_criterion=self.criterion,
            search_method=self.method,
            n_attempted=n_attempted,
            best_seasonal_order=best_order_pair[1] if self.s > 0 else None,
            candidate_seasonal_orders=seasonal_orders if self.s > 0 else None,
            search_messages=search_messages,
        )

        self.result_ = auto_result
        return auto_result


class AutoGARCH(_BaseAutoModel):
    """Auto GARCH-family model selection via grid search.

    Searches over a user-specified range of ``(p, o, q)`` combinations,
    selecting the order that minimises the chosen information criterion.

    Supports all GARCH family variants:
    - Standard GARCH / ARCH / GJR-GARCH (``vol="GARCH"``, default)
    - EGARCH (``vol="EGARCH"``)
    - IGARCH (``igarch=True``)
    - GARCH-M / ARCH-in-mean (``garch_m=True``)

    Parameters
    ----------
    data : array-like
        Time series data (1-D).
    p : tuple[int, int]
        ARCH order range ``(min, max)``. Default ``(1, 4)``.
    q : tuple[int, int]
        GARCH order range ``(min, max)``. ``(0, 0)`` = pure ARCH only.
        Default ``(0, 4)``.
    o : tuple[int, int]
        Asymmetric (GJR) order range ``(min, max)``. Default ``(0, 0)``
        (standard symmetric GARCH only). Set to e.g. ``(0, 1)`` to
        compare symmetric vs asymmetric models.
    vol : str
        Volatility model type: ``"GARCH"`` (default, covers ARCH/GARCH/
        GJR-GARCH) or ``"EGARCH"``.
    mean : str
        Mean model: ``"Constant"``, ``"Zero"``, ``"AR"``, etc.
    dist : str
        Innovation distribution: ``"normal"``, ``"t"``, ``"skewt"``,
        ``"ged"``.
    criterion : str
        ``"aic"``, ``"bic"``, ``"hqic"``, or ``"aicc"``.
    method : str
        Search strategy. Currently only ``"grid"``.
    igarch : bool
        IGARCH constraint estimation (``sum(alpha)+sum(beta)=1``).
        Default ``False``.  Mutually exclusive with ``vol="EGARCH"``
        and ``garch_m=True``.
    garch_m : bool
        GARCH-in-Mean (ARCH-in-mean). Default ``False``.  Mutually
        exclusive with ``vol="EGARCH"`` and ``igarch=True``.
    garch_m_form : str
        Form for GARCH-M: ``"vol"``, ``"var"``, or ``"log"``.
        Default ``"vol"``.  Only used when ``garch_m=True``.
    ar_lags : int or list, optional
        AR lags for the mean equation (only used with ``garch_m=True``).
    exog : array-like, optional
        Exogenous regressors for the mean equation.
    dates : datetime-like sequence, optional
        Strict sample dates. A Series DatetimeIndex is inferred automatically.
        Array inputs may provide dates explicitly.
    missing : {"raise", "drop"}
        Joint non-finite policy for data and exog. ``"drop"`` records removed
        zero-based rows in :attr:`dropped_positions`. Default ``"raise"``.
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
                f"AutoGARCH {context} with exog requires explicit future "
                "or pre-sample exogenous values"
            )

    def __init__(
        self,
        data,
        p=(1, 4),
        q=(0, 4),
        o=(0, 0),
        vol="GARCH",
        mean="Constant",
        dist="normal",
        criterion="aic",
        method="grid",
        igarch=False,
        garch_m=False,
        garch_m_form="vol",
        ar_lags=None,
        exog=None,
        dates=None,
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
            raw_data = raw_data[valid_rows]
            exog = None if exog is None else exog[valid_rows]
            if model_dates is not None:
                model_dates = model_dates[valid_rows].copy()
        self.missing = missing
        self.dropped_positions = dropped_positions
        self.dates = model_dates
        self.data = self._validate_params(raw_data, criterion, method)
        self.criterion = criterion
        self.method = method

        # --- GARCH-specific validation ---
        if vol not in _VOL_TYPES:
            raise ValueError(f"vol must be one of {sorted(_VOL_TYPES)}, got {vol!r}")
        if garch_m and garch_m_form not in _GARCH_M_FORMS:
            raise ValueError(
                f"garch_m_form must be one of {sorted(_GARCH_M_FORMS)}, "
                f"got {garch_m_form!r}"
            )
        if igarch and vol == "EGARCH":
            raise ValueError(
                "IGARCH is not supported for EGARCH models. "
                "Use vol='GARCH' for IGARCH estimation."
            )
        if igarch and garch_m:
            raise ValueError("IGARCH is not supported for GARCH-M (garch_m=True).")
        if garch_m and vol == "EGARCH":
            raise ValueError(
                "GARCH-M is not supported for EGARCH models. "
                "Use vol='GARCH' for ARCH-in-mean estimation."
            )

        self.p_range = self._validate_range(p, "p", min_val=1)
        self.q_range = self._validate_range(q, "q", min_val=0)
        self.o_range = self._validate_range(o, "o", min_val=0)
        self.vol = vol
        self.mean = mean
        self.dist = dist
        self.igarch = igarch
        self.garch_m = garch_m
        self.garch_m_form = garch_m_form
        self.ar_lags = ar_lags
        self.exog = exog

    @staticmethod
    def _validate_range(rng, name, min_val=0):
        """Validate and convert a (min, max) range tuple."""
        if not isinstance(rng, (tuple, list)) or len(rng) != 2:
            raise ValueError(f"{name} must be a (min, max) tuple, got {rng}")
        lo, hi = int(rng[0]), int(rng[1])
        if lo < min_val:
            raise ValueError(f"{name} min must be >= {min_val}, got {lo}")
        if lo > hi:
            raise ValueError(f"{name}: min ({lo}) must be <= max ({hi})")
        return (lo, hi)

    def fit(self):
        """Run grid search and return the best model.

        Returns
        -------
        AutoModelResult
        """
        import itertools

        from Ts.TsModels._garch import GARCH

        p_lo, p_hi = self.p_range
        q_lo, q_hi = self.q_range
        o_lo, o_hi = self.o_range

        orders = itertools.product(
            range(p_lo, p_hi + 1),
            range(o_lo, o_hi + 1),
            range(q_lo, q_hi + 1),
        )

        def build_model(order):
            return GARCH(
                self.data,
                p=order[0],
                o=order[1],
                q=order[2],
                vol=self.vol,
                mean=self.mean,
                dist=self.dist,
                igarch=self.igarch,
                garch_m=self.garch_m,
                garch_m_form=self.garch_m_form,
                ar_lags=self.ar_lags,
                exog=self.exog,
                dates=self.dates,
                compare_lags=False,
            )

        (
            best_result,
            best_order,
            candidate_results,
            candidate_orders,
            n_attempted,
            search_messages,
        ) = self._run_grid_search(self.data, orders, build_model, self.criterion)

        criterion_values = [
            _get_criterion_value(r, self.criterion) for r in candidate_results
        ]

        auto_result = AutoModelResult.from_search(
            best_result=best_result,
            best_order=best_order,
            candidate_results=candidate_results,
            candidate_orders=candidate_orders,
            criterion_values=criterion_values,
            selection_criterion=self.criterion,
            search_method=self.method,
            n_attempted=n_attempted,
            search_messages=search_messages,
        )

        self.result_ = auto_result
        return auto_result
