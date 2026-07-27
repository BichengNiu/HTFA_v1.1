"""
explore.core - 核心工具模块

提供数据验证、序列处理等基础功能
"""

from dashboard.explore.core.constants import (
    DEFAULT_AGG_METHOD,
    DEFAULT_DTW_WINDOW,
    DEFAULT_KL_BINS,
    DEFAULT_KL_SMOOTHING_ALPHA,
    DEFAULT_MAX_LAGS,
    DEFAULT_STANDARDIZATION_METHOD,
    FREQUENCY_MAPPINGS,
    FREQUENCY_PRIORITY,
    MIN_POINTS_PER_BIN,
    MIN_SAMPLES_ADF,
    MIN_SAMPLES_CORRELATION,
    MIN_SAMPLES_KL_DIVERGENCE,
    MIN_SAMPLES_WIN_RATE,
    TIMEDELTA_TOLERANCE_DAYS,
)
from dashboard.explore.core.series_utils import (
    clean_dataframe_columns,
    clean_numeric_series,
    get_lagged_series_slices,
    get_lagged_slices,
    identify_time_column,
    prepare_time_index,
)
from dashboard.explore.core.validation import (
    ValidationResult,
    validate_analysis_inputs,
    validate_series,
    validate_series_pair,
)

__all__ = [
    # constants - 默认参数
    'DEFAULT_AGG_METHOD',
    'DEFAULT_DTW_WINDOW',
    'DEFAULT_KL_BINS',
    'DEFAULT_KL_SMOOTHING_ALPHA',
    'DEFAULT_MAX_LAGS',
    'DEFAULT_STANDARDIZATION_METHOD',
    'FREQUENCY_MAPPINGS',
    'FREQUENCY_PRIORITY',
    'MIN_POINTS_PER_BIN',
    # constants - 数据验证常量
    'MIN_SAMPLES_ADF',
    'MIN_SAMPLES_CORRELATION',
    'MIN_SAMPLES_KL_DIVERGENCE',
    'MIN_SAMPLES_WIN_RATE',
    # constants - 时间序列常量
    'TIMEDELTA_TOLERANCE_DAYS',
    # validation
    'ValidationResult',
    'clean_dataframe_columns',
    # series_utils
    'clean_numeric_series',
    'get_lagged_series_slices',
    'get_lagged_slices',
    'identify_time_column',
    'prepare_time_index',
    'validate_analysis_inputs',
    'validate_series',
    'validate_series_pair',
]
