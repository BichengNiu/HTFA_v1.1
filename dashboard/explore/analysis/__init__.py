# -*- coding: utf-8 -*-
"""
explore.analysis - 时间序列分析模块

提供各类时间序列分析功能
"""

from dashboard.explore.analysis.stationarity import (
    run_stationarity_tests, test_and_process_stationarity,
    run_adf_test, apply_variable_transformations,
    auto_detect_differencing_options, apply_automated_transformations,
    OPERATIONS
)
from dashboard.explore.analysis.lead_lag import perform_combined_lead_lag_analysis, get_detailed_lag_data_for_candidate
from dashboard.explore.analysis.dtw_batch import perform_batch_dtw_calculation

__all__ = [
    # 平稳性分析
    'run_stationarity_tests',
    'test_and_process_stationarity',
    'run_adf_test',
    'apply_variable_transformations',
    'auto_detect_differencing_options',
    'apply_automated_transformations',
    'OPERATIONS',

    # 领先滞后分析
    'perform_combined_lead_lag_analysis',
    'get_detailed_lag_data_for_candidate',

    # DTW批量分析
    'perform_batch_dtw_calculation',
]
