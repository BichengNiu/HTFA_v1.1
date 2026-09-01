"""SARIMAX 模型 UI 共享状态与结果缓存失效逻辑。"""

from __future__ import annotations

from collections.abc import Mapping

from dashboard.core.ui.utils.state_helpers import NamespacedStateManager
from dashboard.models.common.state import ModelStateLifecycle

# 所有 SARIMAX 页面共用的会话状态命名空间。
state = NamespacedStateManager("model_analysis.sarimax")

# 训练 / 分析 / 预测环节的 widget 键。
MODEL_WIDGET_KEYS = (
    "sarimax_target_select",
    "sarimax_exog_select",
    "sarimax_train_forecast_window",
    "sarimax_data_preprocessing",
    "sarimax_response_log",
    "sarimax_model_family",
    "sarimax_config_mode",
    "sarimax_p",
    "sarimax_d",
    "sarimax_q",
    "sarimax_P",
    "sarimax_D",
    "sarimax_Q",
    "sarimax_s",
    "sarimax_ar_lags",
    "sarimax_ma_lags",
    "sarimax_seasonal_ar_lags",
    "sarimax_seasonal_ma_lags",
    "sarimax_exog_operators",
    "sarimax_trend_components",
    "sarimax_method",
    "sarimax_maxiter",
    "sarimax_cov_type",
    "sarimax_enforce_stationarity",
    "sarimax_enforce_invertibility",
    "sarimax_auto_p_range",
    "sarimax_auto_d_range",
    "sarimax_auto_q_range",
    "sarimax_auto_P_range",
    "sarimax_auto_D_range",
    "sarimax_auto_Q_range",
    "sarimax_auto_s",
    "sarimax_auto_exog_operators",
    "sarimax_auto_trend_components",
    "sarimax_auto_selection_criterion",
    "sarimax_auto_selection_model",
    "sarimax_auto_method",
    "sarimax_auto_maxiter",
    "sarimax_auto_cov_type",
    "sarimax_auto_enforce_stationarity",
    "sarimax_auto_enforce_invertibility",
    "sarimax_rdl_error_p",
    "sarimax_rdl_error_d",
    "sarimax_rdl_error_q",
    "sarimax_rdl_error_P",
    "sarimax_rdl_error_D",
    "sarimax_rdl_error_Q",
    "sarimax_rdl_error_s",
    "sarimax_rdl_error_trend_components",
    "sarimax_rdl_error_method",
    "sarimax_rdl_error_maxiter",
    "sarimax_rdl_error_cov_type",
    "sarimax_rdl_error_enforce_stationarity",
    "sarimax_rdl_error_enforce_invertibility",
    "sarimax_rdl_auto_error_p_range",
    "sarimax_rdl_auto_error_d_range",
    "sarimax_rdl_auto_error_q_range",
    "sarimax_rdl_auto_error_P_range",
    "sarimax_rdl_auto_error_D_range",
    "sarimax_rdl_auto_error_Q_range",
    "sarimax_rdl_auto_error_s",
    "sarimax_rdl_auto_error_trend_components",
    "sarimax_rdl_auto_error_criterion",
    "sarimax_rdl_auto_error_enforce_stationarity",
    "sarimax_rdl_auto_error_enforce_invertibility",
    "sarimax_rdl_input_table",
    "sarimax_rdl_advanced_table",
    "sarimax_rdl_enforce_stability",
    "sarimax_ardl_target_lag",
    "sarimax_ardl_trend_components",
    "sarimax_ardl_causal",
    "sarimax_ardl_seasonal",
    "sarimax_ardl_period",
    "sarimax_ardl_input_table",
    "sarimax_ardl_hold_back",
    "sarimax_ardl_cov_type",
    "sarimax_auto_ardl_target_lag",
    "sarimax_auto_ardl_trend_components",
    "sarimax_auto_ardl_causal",
    "sarimax_auto_ardl_seasonal",
    "sarimax_auto_ardl_period",
    "sarimax_auto_ardl_input_table",
    "sarimax_auto_ardl_hold_back",
    "sarimax_auto_ardl_cov_type",
    "sarimax_auto_ardl_criterion",
    "sarimax_auto_ardl_search_method",
    "sarimax_fit_button",
    "sarimax_diag_download",
    "sarimax_innovation_irf_steps",
    "sarimax_forecast_window",
    "sarimax_forecast_alpha",
    "sarimax_forecast_dynamic",
    "sarimax_forecast_ci",
    "sarimax_future_exog_editor",
    "sarimax_forecast_button",
    "sarimax_forecast_download",
)

# SARIMAX 模型页的 Streamlit widget 键。
WIDGET_KEYS = MODEL_WIDGET_KEYS

# 跨模块切换时保留用户可编辑的页面输入；提交、下载与运行按钮不保存，
# 以免切回页面后重复执行操作。
PERSISTENT_WIDGET_KEYS = tuple(
    key
    for key in WIDGET_KEYS
    if not key.endswith(("_button", "_download"))
    and key
    not in {
        "sarimax_rdl_input_table",
        "sarimax_rdl_advanced_table",
        "sarimax_ardl_input_table",
        "sarimax_auto_ardl_input_table",
        "sarimax_exog_operators",
        "sarimax_auto_exog_operators",
        "sarimax_future_exog_editor",
    }
)

# 数据集变化时清除模型页的 widget 状态。
DATASET_REPLACED_WIDGET_KEYS = MODEL_WIDGET_KEYS

RESULT_KEYS = (
    "fitted_result",
    "fit_signature",
    "diagnostics_table",
    "diagnostics_signature",
    "forecast",
    "forecast_signature",
)

_STATE_LIFECYCLE = ModelStateLifecycle(
    store=state,
    fit_result_keys=("fitted_result", "fit_signature"),
    downstream_result_keys=(
        "diagnostics_table",
        "diagnostics_signature",
        "forecast",
        "forecast_signature",
        "forecast_widget_fit_signature",
    ),
    widget_keys=WIDGET_KEYS,
)


def clear_fit_results() -> None:
    """清除全部拟合与派生结果（参数变化时调用）。"""
    _STATE_LIFECYCLE.clear_fit_results()


def store_fit_result(result, signature) -> None:
    """发布拟合结果、签名并清除依赖旧结果的下游状态。"""
    _STATE_LIFECYCLE.store_fit_result(result, signature)


def clear_downstream_results() -> None:
    """清除当前模型选择之后的诊断与预测结果。"""
    _STATE_LIFECYCLE.clear_downstream_results()


def store_downstream_result(
    result_key: str,
    result,
    signature_key: str,
    signature,
) -> None:
    """发布下游结果与签名，统一校验状态键归属。"""
    _STATE_LIFECYCLE.store_downstream_result(
        result_key,
        result,
        signature_key,
        signature,
    )


def clear_downstream_result(result_key: str, signature_key: str) -> None:
    """清除一个下游结果及其签名。"""
    _STATE_LIFECYCLE.clear_downstream_result(result_key, signature_key)


def restore_result_state(
    values: Mapping[str, object],
    *,
    keys: tuple[str, ...] = RESULT_KEYS,
) -> None:
    """恢复交接快照中的结果状态。"""
    _STATE_LIFECYCLE.restore_result_state(values, keys=keys)


def clear_widget_state(st_obj, keys: tuple[str, ...] = WIDGET_KEYS) -> None:
    """删除指定 Streamlit widget 的会话值，避免旧值残留。"""
    _STATE_LIFECYCLE.clear_widget_state(st_obj, keys=keys)


__all__ = [
    "DATASET_REPLACED_WIDGET_KEYS",
    "MODEL_WIDGET_KEYS",
    "PERSISTENT_WIDGET_KEYS",
    "RESULT_KEYS",
    "WIDGET_KEYS",
    "clear_downstream_result",
    "clear_downstream_results",
    "clear_fit_results",
    "clear_widget_state",
    "restore_result_state",
    "store_downstream_result",
    "store_fit_result",
    "state",
]
