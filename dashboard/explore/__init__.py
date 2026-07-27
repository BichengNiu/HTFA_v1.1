"""时间序列探索分析工具。

公共兼容接口按需加载，避免导入轻量 core 模块时初始化 Ts、Matplotlib
和 DTW 等无关依赖。应用内部代码应优先从具体子模块直接导入。
"""

from __future__ import annotations

from importlib import import_module

_LAZY_EXPORTS = {
    # core.constants
    "DEFAULT_KL_BINS": ("dashboard.explore.core.constants", "DEFAULT_KL_BINS"),
    "FREQUENCY_MAPPINGS": (
        "dashboard.explore.core.constants",
        "FREQUENCY_MAPPINGS",
    ),
    "FREQUENCY_PRIORITY": (
        "dashboard.explore.core.constants",
        "FREQUENCY_PRIORITY",
    ),
    "MIN_SAMPLES_ADF": ("dashboard.explore.core.constants", "MIN_SAMPLES_ADF"),
    "MIN_SAMPLES_CORRELATION": (
        "dashboard.explore.core.constants",
        "MIN_SAMPLES_CORRELATION",
    ),
    "MIN_SAMPLES_KL_DIVERGENCE": (
        "dashboard.explore.core.constants",
        "MIN_SAMPLES_KL_DIVERGENCE",
    ),
    # core.validation
    "ValidationResult": (
        "dashboard.explore.core.validation",
        "ValidationResult",
    ),
    "validate_series": ("dashboard.explore.core.validation", "validate_series"),
    "validate_series_pair": (
        "dashboard.explore.core.validation",
        "validate_series_pair",
    ),
    # core.series_utils
    "clean_numeric_series": (
        "dashboard.explore.core.series_utils",
        "clean_numeric_series",
    ),
    "get_lagged_series_slices": (
        "dashboard.explore.core.series_utils",
        "get_lagged_series_slices",
    ),
    "get_lagged_slices": (
        "dashboard.explore.core.series_utils",
        "get_lagged_slices",
    ),
    "identify_time_column": (
        "dashboard.explore.core.series_utils",
        "identify_time_column",
    ),
    "prepare_time_index": (
        "dashboard.explore.core.series_utils",
        "prepare_time_index",
    ),
    # metrics
    "calculate_dtw_distance": (
        "dashboard.explore.metrics.dtw",
        "calculate_dtw_distance",
    ),
    "calculate_dtw_path": (
        "dashboard.explore.metrics.dtw",
        "calculate_dtw_path",
    ),
    "calculate_kl_divergence_series": (
        "dashboard.explore.metrics.kl_divergence",
        "calculate_kl_divergence_series",
    ),
    "calculate_time_lagged_correlation": (
        "dashboard.explore.metrics.correlation",
        "calculate_time_lagged_correlation",
    ),
    "find_optimal_lag": (
        "dashboard.explore.metrics.correlation",
        "find_optimal_lag",
    ),
    "kl_divergence": (
        "dashboard.explore.metrics.kl_divergence",
        "kl_divergence",
    ),
    "series_to_distribution": (
        "dashboard.explore.metrics.kl_divergence",
        "series_to_distribution",
    ),
    # analysis.stationarity
    "TEST_LABELS": (
        "dashboard.explore.analysis.stationarity",
        "TEST_LABELS",
    ),
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
    # other analysis
    "get_detailed_lag_data_for_candidate": (
        "dashboard.explore.analysis.lead_lag",
        "get_detailed_lag_data_for_candidate",
    ),
    "perform_batch_dtw_calculation": (
        "dashboard.explore.analysis.dtw_batch",
        "perform_batch_dtw_calculation",
    ),
    "perform_combined_lead_lag_analysis": (
        "dashboard.explore.analysis.lead_lag",
        "perform_combined_lead_lag_analysis",
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
    # preprocessing
    "align_series_for_analysis": (
        "dashboard.explore.preprocessing.frequency_alignment",
        "align_series_for_analysis",
    ),
    "format_alignment_report": (
        "dashboard.explore.preprocessing.frequency_alignment",
        "format_alignment_report",
    ),
    "infer_series_frequency": (
        "dashboard.explore.preprocessing.frequency_alignment",
        "infer_series_frequency",
    ),
    "standardize_series": (
        "dashboard.explore.preprocessing.standardization",
        "standardize_series",
    ),
    "standardize_series_pair": (
        "dashboard.explore.preprocessing.standardization",
        "standardize_series_pair",
    ),
}

__all__ = tuple(_LAZY_EXPORTS)


def __getattr__(name: str):
    """按需解析旧版包根导出。"""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
