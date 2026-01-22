# -*- coding: utf-8 -*-
"""
explore.core - 核心工具模块

提供数据验证、序列处理等基础功能
"""

from dashboard.explore.core.constants import *
from dashboard.explore.core.validation import *
from dashboard.explore.core.series_utils import *

__all__ = [
    # constants - 数据验证常量
    'MIN_SAMPLES_ADF',
    'MIN_SAMPLES_CORRELATION',
    'MIN_SAMPLES_KL_DIVERGENCE',
    'MIN_SAMPLES_WIN_RATE',
    'DEFAULT_KL_BINS',
    'DEFAULT_KL_SMOOTHING_ALPHA',
    'MIN_POINTS_PER_BIN',

    # constants - 时间序列常量
    'TIMEDELTA_TOLERANCE_DAYS',
    'FREQUENCY_MAPPINGS',
    'FREQUENCY_PRIORITY',

    # constants - 默认参数
    'DEFAULT_AGG_METHOD',
    'DEFAULT_STANDARDIZATION_METHOD',
    'DEFAULT_MAX_LAGS',
    'DEFAULT_DTW_WINDOW',

    # validation
    'ValidationResult',
    'validate_series',
    'validate_series_pair',
    'validate_analysis_inputs',

    # series_utils
    'clean_numeric_series',
    'clean_dataframe_columns',
    'identify_time_column',
    'prepare_time_index',
    'get_lagged_slices',
    'get_lagged_series_slices',
]
