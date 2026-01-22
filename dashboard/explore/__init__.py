# -*- coding: utf-8 -*-
"""
时间序列探索分析工具模块

重构后的模块化架构：
- core: 核心工具（常量、验证、序列处理）
- metrics: 度量计算（相关性、KL散度、DTW）
- analysis: 分析功能（平稳性、领先滞后、胜率）
- preprocessing: 预处理（频率对齐、标准化）
"""

# ==================== Core模块 ====================
from dashboard.explore.core import (
    # 常量
    MIN_SAMPLES_ADF,
    MIN_SAMPLES_CORRELATION,
    MIN_SAMPLES_KL_DIVERGENCE,
    DEFAULT_KL_BINS,
    FREQUENCY_MAPPINGS,
    FREQUENCY_PRIORITY,

    # 验证
    ValidationResult,
    validate_series,
    validate_series_pair,

    # 序列工具
    clean_numeric_series,
    identify_time_column,
    prepare_time_index,
    get_lagged_slices,
    get_lagged_series_slices,
)

# ==================== Metrics模块 ====================
from dashboard.explore.metrics import (
    # KL散度
    series_to_distribution,
    kl_divergence,
    calculate_kl_divergence_series,

    # 相关性
    calculate_time_lagged_correlation,
    find_optimal_lag,

    # DTW
    calculate_dtw_distance,
    calculate_dtw_path,
)

# ==================== Analysis模块 ====================
from dashboard.explore.analysis import (
    # 平稳性分析
    run_stationarity_tests,
    test_and_process_stationarity,
    run_adf_test,
    apply_variable_transformations,
    OPERATIONS,

    # 领先滞后分析
    perform_combined_lead_lag_analysis,
    get_detailed_lag_data_for_candidate,

    # DTW批量分析
    perform_batch_dtw_calculation,
)

# ==================== Preprocessing模块 ====================
from dashboard.explore.preprocessing import (
    # 频率对齐
    infer_series_frequency,
    align_series_for_analysis,
    format_alignment_report,

    # 标准化
    standardize_series,
    standardize_series_pair,
)

__all__ = [
    # Core - 常量
    'MIN_SAMPLES_ADF',
    'MIN_SAMPLES_CORRELATION',
    'MIN_SAMPLES_KL_DIVERGENCE',
    'DEFAULT_KL_BINS',
    'FREQUENCY_MAPPINGS',
    'FREQUENCY_PRIORITY',

    # Core - 验证
    'ValidationResult',
    'validate_series',
    'validate_series_pair',

    # Core - 序列工具
    'clean_numeric_series',
    'identify_time_column',
    'prepare_time_index',
    'get_lagged_slices',
    'get_lagged_series_slices',

    # Metrics - KL散度
    'series_to_distribution',
    'kl_divergence',
    'calculate_kl_divergence_series',

    # Metrics - 相关性
    'calculate_time_lagged_correlation',
    'find_optimal_lag',

    # Metrics - DTW
    'calculate_dtw_distance',
    'calculate_dtw_path',

    # Analysis - 平稳性
    'run_stationarity_tests',
    'test_and_process_stationarity',
    'run_adf_test',
    'apply_variable_transformations',
    'OPERATIONS',

    # Analysis - 领先滞后
    'perform_combined_lead_lag_analysis',
    'get_detailed_lag_data_for_candidate',

    # Analysis - DTW批量分析
    'perform_batch_dtw_calculation',

    # Preprocessing - 频率对齐
    'infer_series_frequency',
    'align_series_for_analysis',
    'format_alignment_report',

    # Preprocessing - 标准化
    'standardize_series',
    'standardize_series_pair',
]

# 注意：get_standardization_description 已移除（未实现）