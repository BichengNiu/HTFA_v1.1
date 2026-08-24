"""SARIMAX 模型 UI 共享状态与结果缓存失效逻辑。"""

from __future__ import annotations

from typing import Any

from data_overview.ui.widget_keys import (
    CHART_WIDGET_KEYS,
    READ_WIDGET_KEYS,
    SELECTOR_WIDGET_KEYS,
    TABLE_WIDGET_KEYS,
)

from dashboard.core.ui.utils.state_helpers import NamespacedStateManager

# 所有 SARIMAX 页面共用的会话状态命名空间。
state = NamespacedStateManager("model_analysis.sarimax")

# 训练 / 分析 / 预测环节的 widget 键（数据概览的键在 ui/overview/widget_keys.py）。
MODEL_WIDGET_KEYS = (
    "sarimax_target_select",
    "sarimax_exog_select",
    "sarimax_model_family",
    "sarimax_config_mode",
    "sarimax_p",
    "sarimax_d",
    "sarimax_q",
    "sarimax_P",
    "sarimax_D",
    "sarimax_Q",
    "sarimax_s",
    "sarimax_trend",
    "sarimax_log",
    "sarimax_method",
    "sarimax_maxiter",
    "sarimax_cov_type",
    "sarimax_enforce_stationarity",
    "sarimax_enforce_invertibility",
    "sarimax_auto_p_min",
    "sarimax_auto_p_max",
    "sarimax_auto_d_min",
    "sarimax_auto_d_max",
    "sarimax_auto_q_min",
    "sarimax_auto_q_max",
    "sarimax_auto_P_min",
    "sarimax_auto_P_max",
    "sarimax_auto_D_min",
    "sarimax_auto_D_max",
    "sarimax_auto_Q_min",
    "sarimax_auto_Q_max",
    "sarimax_auto_s",
    "sarimax_auto_trend",
    "sarimax_auto_criterion",
    "sarimax_auto_log",
    "sarimax_auto_enforce_stationarity",
    "sarimax_auto_enforce_invertibility",
    "sarimax_rdl_error_p",
    "sarimax_rdl_error_d",
    "sarimax_rdl_error_q",
    "sarimax_rdl_error_P",
    "sarimax_rdl_error_D",
    "sarimax_rdl_error_Q",
    "sarimax_rdl_error_s",
    "sarimax_rdl_error_trend",
    "sarimax_rdl_error_log",
    "sarimax_rdl_error_method",
    "sarimax_rdl_error_maxiter",
    "sarimax_rdl_error_cov_type",
    "sarimax_rdl_error_enforce_stationarity",
    "sarimax_rdl_error_enforce_invertibility",
    "sarimax_rdl_auto_error_p_min",
    "sarimax_rdl_auto_error_p_max",
    "sarimax_rdl_auto_error_d_min",
    "sarimax_rdl_auto_error_d_max",
    "sarimax_rdl_auto_error_q_min",
    "sarimax_rdl_auto_error_q_max",
    "sarimax_rdl_auto_error_P_min",
    "sarimax_rdl_auto_error_P_max",
    "sarimax_rdl_auto_error_D_min",
    "sarimax_rdl_auto_error_D_max",
    "sarimax_rdl_auto_error_Q_min",
    "sarimax_rdl_auto_error_Q_max",
    "sarimax_rdl_auto_error_s",
    "sarimax_rdl_auto_error_trend",
    "sarimax_rdl_auto_error_criterion",
    "sarimax_rdl_auto_error_log",
    "sarimax_rdl_auto_error_enforce_stationarity",
    "sarimax_rdl_auto_error_enforce_invertibility",
    "sarimax_rdl_input_table",
    "sarimax_rdl_advanced_table",
    "sarimax_rdl_enforce_stability",
    "sarimax_ardl_target_lag",
    "sarimax_ardl_trend",
    "sarimax_ardl_causal",
    "sarimax_ardl_seasonal",
    "sarimax_ardl_period",
    "sarimax_ardl_input_table",
    "sarimax_ardl_log",
    "sarimax_ardl_hold_back",
    "sarimax_ardl_cov_type",
    "sarimax_auto_ardl_target_lag",
    "sarimax_auto_ardl_trend",
    "sarimax_auto_ardl_causal",
    "sarimax_auto_ardl_seasonal",
    "sarimax_auto_ardl_period",
    "sarimax_auto_ardl_input_table",
    "sarimax_auto_ardl_log",
    "sarimax_auto_ardl_hold_back",
    "sarimax_auto_ardl_cov_type",
    "sarimax_auto_ardl_criterion",
    "sarimax_auto_ardl_search_method",
    "sarimax_fit_button",
    "sarimax_diag_lags",
    "sarimax_diag_button",
    "sarimax_diag_download",
    "sarimax_forecast_steps",
    "sarimax_forecast_alpha",
    "sarimax_forecast_dynamic",
    "sarimax_future_exog_editor",
    "sarimax_forecast_button",
    "sarimax_forecast_download",
)

# 全部 Streamlit widget 键；换文件或换变量时需要清除，
# 避免旧 widget 值被 Streamlit 自动恢复。读取设置也纳入汇总，
# 便于宿主页面统一管理。
WIDGET_KEYS = (
    SELECTOR_WIDGET_KEYS
    + READ_WIDGET_KEYS
    + CHART_WIDGET_KEYS
    + TABLE_WIDGET_KEYS
    + MODEL_WIDGET_KEYS
)

# 数据集变化时清除旧图形、表格和模型状态，但保留本次刚输入的读取设置。
# 变量多选同样保留，由 data_overview.ui.selectors 按新变量名自动过滤。
DATASET_REPLACED_WIDGET_KEYS = (
    CHART_WIDGET_KEYS + TABLE_WIDGET_KEYS + MODEL_WIDGET_KEYS
)

RESULT_KEYS = (
    "fitted_result",
    "fit_signature",
    "diagnostics_table",
    "diagnostics_signature",
    "forecast",
    "forecast_signature",
)


def clear_fit_results() -> None:
    """清除全部拟合与派生结果（参数变化时调用）。"""
    for key in RESULT_KEYS:
        state.set(key, None)


def clear_dataset_state() -> None:
    """清除数据集与变量选择状态（换文件或清空上传时调用）。"""
    state.set("dataset", None)
    state.set("source_fingerprint", None)
    state.set("file_fingerprint", None)
    state.set("file_name", None)
    state.set("target_variable", None)
    state.set("exog_variables", ())
    clear_fit_results()


def clear_widget_state(st_obj, keys: tuple[str, ...] = WIDGET_KEYS) -> None:
    """删除指定 Streamlit widget 的会话值，避免旧值残留。"""
    session = getattr(st_obj, "session_state", None)
    if session is None:
        return
    for key in keys:
        session.pop(key, None)


def get_fitted_result() -> Any:
    """返回当前有效的拟合结果对象（无结果时为 None）。"""
    return state.get("fitted_result")


__all__ = [
    "DATASET_REPLACED_WIDGET_KEYS",
    "MODEL_WIDGET_KEYS",
    "RESULT_KEYS",
    "WIDGET_KEYS",
    "clear_dataset_state",
    "clear_fit_results",
    "clear_widget_state",
    "get_fitted_result",
    "state",
]
