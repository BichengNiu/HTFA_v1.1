# -*- coding: utf-8 -*-
"""
explore.analysis - 时间序列分析模块

提供各类时间序列分析功能
"""

from dashboard.explore.analysis.stationarity import (
    TEST_LABELS,
    TEST_TREND_LABELS,
    TEST_TREND_OPTIONS,
    TRANSFORMATIONS,
    create_correlogram_figure,
    create_time_series_figure,
    numeric_variable_names,
    prepare_selected_series,
    resolve_correlation_lags,
    run_adf_test,
    run_kpss_test,
    run_selected_stationarity_tests,
    run_stationarity_tests,
    summarize_series,
    transform_series,
)
from dashboard.explore.analysis.lead_lag import perform_combined_lead_lag_analysis, get_detailed_lag_data_for_candidate
from dashboard.explore.analysis.dtw_batch import perform_batch_dtw_calculation
from dashboard.explore.analysis.structural_break import (
    STRUCTURAL_BREAK_LAG_METHODS,
    STRUCTURAL_BREAK_MODELS,
    run_zivot_andrews_test,
)

__all__ = [
    # 平稳性检验
    'TEST_LABELS',
    'TEST_TREND_LABELS',
    'TEST_TREND_OPTIONS',
    'TRANSFORMATIONS',
    'create_correlogram_figure',
    'create_time_series_figure',
    'numeric_variable_names',
    'prepare_selected_series',
    'resolve_correlation_lags',
    'run_stationarity_tests',
    'run_adf_test',
    'run_kpss_test',
    'run_selected_stationarity_tests',
    'summarize_series',
    'transform_series',
    'STRUCTURAL_BREAK_LAG_METHODS',
    'STRUCTURAL_BREAK_MODELS',
    'run_zivot_andrews_test',

    # 领先滞后分析
    'perform_combined_lead_lag_analysis',
    'get_detailed_lag_data_for_candidate',

    # DTW批量分析
    'perform_batch_dtw_calculation',
]
