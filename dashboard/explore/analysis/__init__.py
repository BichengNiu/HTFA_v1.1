"""可测试的时间序列分析实现。

从具体子模块导入所需功能，避免分析包初始化时加载所有统计依赖。
"""

from importlib import import_module

_LAZY_EXPORTS = {
    "TEST_LABELS": ("dashboard.explore.analysis.stationarity", "TEST_LABELS"),
    "TEST_TREND_LABELS": (
        "dashboard.explore.analysis.stationarity",
        "TEST_TREND_LABELS",
    ),
    "TEST_TREND_OPTIONS": (
        "dashboard.explore.analysis.stationarity",
        "TEST_TREND_OPTIONS",
    ),
    "TRANSFORMATIONS": (
        "dashboard.explore.analysis.stationarity",
        "TRANSFORMATIONS",
    ),
    "create_correlogram_figure": (
        "dashboard.explore.analysis.stationarity",
        "create_correlogram_figure",
    ),
    "create_time_series_figure": (
        "dashboard.explore.analysis.stationarity",
        "create_time_series_figure",
    ),
    "numeric_variable_names": (
        "dashboard.explore.analysis.stationarity",
        "numeric_variable_names",
    ),
    "prepare_selected_series": (
        "dashboard.explore.analysis.stationarity",
        "prepare_selected_series",
    ),
    "resolve_correlation_lags": (
        "dashboard.explore.analysis.stationarity",
        "resolve_correlation_lags",
    ),
    "run_adf_test": (
        "dashboard.explore.analysis.stationarity",
        "run_adf_test",
    ),
    "run_kpss_test": (
        "dashboard.explore.analysis.stationarity",
        "run_kpss_test",
    ),
    "run_selected_stationarity_tests": (
        "dashboard.explore.analysis.stationarity",
        "run_selected_stationarity_tests",
    ),
    "run_stationarity_tests": (
        "dashboard.explore.analysis.stationarity",
        "run_stationarity_tests",
    ),
    "summarize_series": (
        "dashboard.explore.analysis.stationarity",
        "summarize_series",
    ),
    "transform_series": (
        "dashboard.explore.analysis.stationarity",
        "transform_series",
    ),
    "perform_combined_lead_lag_analysis": (
        "dashboard.explore.analysis.lead_lag",
        "perform_combined_lead_lag_analysis",
    ),
    "get_detailed_lag_data_for_candidate": (
        "dashboard.explore.analysis.lead_lag",
        "get_detailed_lag_data_for_candidate",
    ),
    "perform_batch_dtw_calculation": (
        "dashboard.explore.analysis.dtw_batch",
        "perform_batch_dtw_calculation",
    ),
    "STRUCTURAL_BREAK_LAG_METHODS": (
        "dashboard.explore.analysis.structural_break",
        "STRUCTURAL_BREAK_LAG_METHODS",
    ),
    "STRUCTURAL_BREAK_MODELS": (
        "dashboard.explore.analysis.structural_break",
        "STRUCTURAL_BREAK_MODELS",
    ),
    "run_zivot_andrews_test": (
        "dashboard.explore.analysis.structural_break",
        "run_zivot_andrews_test",
    ),
}

__all__ = tuple(_LAZY_EXPORTS)


def __getattr__(name: str):
    """按需解析原有分析包导出。"""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
