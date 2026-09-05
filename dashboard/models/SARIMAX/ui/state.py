"""动态回归各模型页的隔离状态与结果生命周期。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from htfa.app.state.session_state import NamespacedStateManager
from dashboard.models.common.state import ModelStateLifecycle


_COMMON_WIDGET_SUFFIXES = (
    "target_select", "exog_select", "train_forecast_window",
    "data_preprocessing", "missing_value_method", "response_log",
    "start_processing_button", "fit_button", "diag_download",
    "innovation_irf_steps", "forecast_window", "forecast_alpha",
    "forecast_dynamic", "forecast_ci", "future_exog_editor", "forecast_button",
    "forecast_download", "forecast_evaluation_download",
    "forecast_backtest_horizon", "forecast_backtest_button",
    "forecast_backtest_download",
    "forecast_training_horizon", "forecast_training_button",
    "forecast_training_download", "forecast_training_rolling_download",
    "forecast_oos_horizon", "forecast_oos_button",
    "forecast_oos_download", "forecast_oos_rolling_download",
)
_SARIMAX_WIDGET_SUFFIXES = (
    "p", "d", "q", "P", "D", "Q", "s", "ar_lags", "ma_lags",
    "seasonal_ar_lags", "seasonal_ma_lags", "exog_operators",
    "trend_components", "method", "maxiter", "cov_type",
    "enforce_stationarity", "enforce_invertibility", "auto_p_range",
    "auto_d_range", "auto_q_range", "auto_P_range", "auto_D_range",
    "auto_Q_range", "auto_s", "auto_exog_operators",
    "auto_trend_components", "auto_selection_criterion", "auto_selection_model",
    "auto_method", "auto_maxiter", "auto_cov_type",
    "auto_enforce_stationarity", "auto_enforce_invertibility",
    "config_mode",
)
_RDL_WIDGET_SUFFIXES = (
    "error_p", "error_d", "error_q", "error_P", "error_D", "error_Q",
    "error_s", "error_trend_components", "error_method", "error_maxiter",
    "error_cov_type", "error_enforce_stationarity", "error_enforce_invertibility",
    "error_ar_lags", "error_ma_lags", "error_seasonal_ar_lags",
    "error_seasonal_ma_lags",
    "input_table", "advanced_table", "enforce_stability",
    "intervention_analysis", "intervention_kind", "intervention_pulse_date",
    "intervention_start",
    "intervention_window",
)
_ARDL_WIDGET_SUFFIXES = (
    "error_p", "error_d", "error_q", "error_P", "error_D", "error_Q",
    "error_s", "error_method", "error_maxiter", "error_cov_type",
    "error_enforce_stationarity", "error_enforce_invertibility",
    "error_ar_lags", "error_ma_lags", "error_seasonal_ar_lags",
    "error_seasonal_ma_lags", "target_lag", "trend_components", "causal",
    "seasonal", "period", "input_table", "hold_back",
)
_TABLE_SUFFIXES = (
    "input_table", "advanced_table", "exog_operators", "future_exog_editor",
)
_RESULT_KEYS = (
    "fitted_result", "fit_signature", "diagnostics_table", "diagnostics_signature",
    "forecast", "forecast_signature",
    "backtest", "backtest_signature",
    "training_evaluation", "training_evaluation_signature",
    "oos_evaluation", "oos_evaluation_signature",
)


@dataclass(frozen=True)
class ModelPageScope:
    """一个模型 Tab 的页面标识、控件前缀和私有状态域。"""

    family: str
    namespace: str
    key_prefix: str
    data_key_prefix: str
    widget_suffixes: tuple[str, ...]
    state: NamespacedStateManager = field(init=False)
    widget_keys: tuple[str, ...] = field(init=False)
    persistent_widget_keys: tuple[str, ...] = field(init=False)
    lifecycle: ModelStateLifecycle = field(init=False, repr=False)

    def __post_init__(self) -> None:
        widget_keys = tuple(dict.fromkeys(
            f"{self.key_prefix}_{suffix}"
            for suffix in _COMMON_WIDGET_SUFFIXES + self.widget_suffixes
        ))
        state = NamespacedStateManager(self.namespace)
        persistent = tuple(
            key for key in widget_keys
            if not key.endswith(("_button", "_download"))
            and not key.endswith(_TABLE_SUFFIXES)
        )
        lifecycle = ModelStateLifecycle(
            store=state,
            fit_result_keys=("fitted_result", "fit_signature"),
            downstream_result_keys=(
                "diagnostics_table", "diagnostics_signature", "forecast",
                "forecast_signature", "forecast_widget_fit_signature",
                "backtest", "backtest_signature",
                "training_evaluation", "training_evaluation_signature",
                "oos_evaluation", "oos_evaluation_signature",
            ),
            widget_keys=widget_keys,
        )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "widget_keys", widget_keys)
        object.__setattr__(self, "persistent_widget_keys", persistent)
        object.__setattr__(self, "lifecycle", lifecycle)

    def key(self, suffix: str) -> str:
        """返回当前模型 Tab 的 Streamlit widget key。"""
        return f"{self.key_prefix}_{suffix}"

    def clear_fit_results(self) -> None:
        self.lifecycle.clear_fit_results()
        self.state.set("fit_config", None)

    def store_fit_result(self, result, signature) -> None:
        self.lifecycle.store_fit_result(result, signature)

    def clear_downstream_result(self, result_key: str, signature_key: str) -> None:
        self.lifecycle.clear_downstream_result(result_key, signature_key)

    def store_downstream_result(self, result_key: str, result, signature_key: str, signature) -> None:
        self.lifecycle.store_downstream_result(result_key, result, signature_key, signature)

    def clear_widget_state(self, st_obj, keys: tuple[str, ...] | None = None) -> None:
        self.lifecycle.clear_widget_state(st_obj, keys=keys)

    def restore_result_state(self, values: Mapping[str, object], *, keys: tuple[str, ...] = _RESULT_KEYS) -> None:
        self.lifecycle.restore_result_state(values, keys=keys)


SARIMAX_SCOPE = ModelPageScope(
    family="SARIMAX", namespace="model_analysis.sarimax", key_prefix="sarimax",
    data_key_prefix="sarimax_model", widget_suffixes=_SARIMAX_WIDGET_SUFFIXES,
)
RDL_SCOPE = ModelPageScope(
    family="RDL", namespace="model_analysis.rdl", key_prefix="rdl",
    data_key_prefix="rdl_model", widget_suffixes=_RDL_WIDGET_SUFFIXES,
)
ARDL_SCOPE = ModelPageScope(
    family="ARDL", namespace="model_analysis.ardl", key_prefix="ardl",
    data_key_prefix="ardl_model", widget_suffixes=_ARDL_WIDGET_SUFFIXES,
)

# 兼容 SARIMAX 独立页交接模块的既有公共名称。
state = SARIMAX_SCOPE.state
MODEL_WIDGET_KEYS = SARIMAX_SCOPE.widget_keys
WIDGET_KEYS = MODEL_WIDGET_KEYS
PERSISTENT_WIDGET_KEYS = SARIMAX_SCOPE.persistent_widget_keys
DATASET_REPLACED_WIDGET_KEYS = MODEL_WIDGET_KEYS
RESULT_KEYS = _RESULT_KEYS


def clear_fit_results() -> None:
    SARIMAX_SCOPE.clear_fit_results()


def store_fit_result(result, signature) -> None:
    SARIMAX_SCOPE.store_fit_result(result, signature)


def clear_downstream_results() -> None:
    SARIMAX_SCOPE.lifecycle.clear_downstream_results()


def store_downstream_result(result_key: str, result, signature_key: str, signature) -> None:
    SARIMAX_SCOPE.store_downstream_result(result_key, result, signature_key, signature)


def clear_downstream_result(result_key: str, signature_key: str) -> None:
    SARIMAX_SCOPE.clear_downstream_result(result_key, signature_key)


def restore_result_state(values: Mapping[str, object], *, keys: tuple[str, ...] = RESULT_KEYS) -> None:
    SARIMAX_SCOPE.restore_result_state(values, keys=keys)


def clear_widget_state(st_obj, keys: tuple[str, ...] = WIDGET_KEYS) -> None:
    SARIMAX_SCOPE.clear_widget_state(st_obj, keys)


__all__ = [
    "ARDL_SCOPE", "DATASET_REPLACED_WIDGET_KEYS", "MODEL_WIDGET_KEYS",
    "ModelPageScope", "PERSISTENT_WIDGET_KEYS", "RDL_SCOPE", "RESULT_KEYS",
    "SARIMAX_SCOPE", "WIDGET_KEYS", "clear_downstream_result",
    "clear_downstream_results", "clear_fit_results", "clear_widget_state",
    "restore_result_state", "state", "store_downstream_result", "store_fit_result",
]
