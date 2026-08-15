"""
explore.core - 核心工具模块

提供数据验证、序列处理等基础功能
"""

from dashboard.explore.core.constants import (
    DEFAULT_AGG_METHOD,
    DEFAULT_KL_SMOOTHING_ALPHA,
    DEFAULT_STANDARDIZATION_METHOD,
    FREQUENCY_MAPPINGS,
    FREQUENCY_PRIORITY,
    MIN_SAMPLES_ADF,
    MIN_SAMPLES_CORRELATION,
    MIN_SAMPLES_KL_DIVERGENCE,
    TIMEDELTA_TOLERANCE_DAYS,
)
from dashboard.explore.core.series_utils import (
    clean_dataframe_columns,
    get_lagged_slices,
    identify_time_column,
    prepare_time_index,
)
from dashboard.explore.core.validation import (
    ValidationResult,
    validate_analysis_inputs,
    validate_series,
)

__all__ = [
    # constants - 默认参数
    'DEFAULT_AGG_METHOD',
    'DEFAULT_KL_SMOOTHING_ALPHA',
    'DEFAULT_STANDARDIZATION_METHOD',
    'FREQUENCY_MAPPINGS',
    'FREQUENCY_PRIORITY',
    # constants - 数据验证常量
    'MIN_SAMPLES_ADF',
    'MIN_SAMPLES_CORRELATION',
    'MIN_SAMPLES_KL_DIVERGENCE',
    # constants - 时间序列常量
    'TIMEDELTA_TOLERANCE_DAYS',
    # validation
    'ValidationResult',
    'clean_dataframe_columns',
    # series_utils
    'get_lagged_slices',
    'identify_time_column',
    'prepare_time_index',
    'validate_analysis_inputs',
    'validate_series',
]
