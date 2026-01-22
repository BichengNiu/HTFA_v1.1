# -*- coding: utf-8 -*-
"""
工具函数模块

包含数据验证、辅助函数和异常处理等工具类。
"""

from .validators import validate_model_data
from .helpers import (
    ensure_numerical_stability,
    safe_matrix_division,
    align_time_series,
    detect_outliers
)
from .exceptions import (
    DecompError,
    ModelLoadError,
    ValidationError,
    ComputationError
)
from .logging_config import get_logger

__all__ = [
    # 验证器
    'validate_model_data',
    # 辅助函数
    'ensure_numerical_stability',
    'safe_matrix_division',
    'align_time_series',
    'detect_outliers',
    # 异常类
    'DecompError',
    'ModelLoadError',
    'ValidationError',
    'ComputationError',
    # 日志
    'get_logger'
]