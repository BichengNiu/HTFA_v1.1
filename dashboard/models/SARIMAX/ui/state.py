"""SARIMAX 模型 UI 共享状态与结果缓存失效逻辑。"""

from __future__ import annotations

from typing import Any

from dashboard.core.ui.utils.state_helpers import NamespacedStateManager

# 所有 SARIMAX 页面共用的会话状态命名空间。
state = NamespacedStateManager("model_analysis.sarimax")

# 全部 Streamlit widget 键；换文件或换变量时需要清除，
# 避免旧 widget 值被 Streamlit 自动恢复。
WIDGET_KEYS = (
    "sarimax_file_uploader",
    "sarimax_target_select",
    "sarimax_exog_select",
    "sarimax_mode_radio",
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
    "RESULT_KEYS",
    "WIDGET_KEYS",
    "clear_dataset_state",
    "clear_fit_results",
    "clear_widget_state",
    "get_fitted_result",
    "state",
]
