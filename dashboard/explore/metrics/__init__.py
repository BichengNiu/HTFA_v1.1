# -*- coding: utf-8 -*-
"""
explore.metrics - 度量计算模块

提供各种时间序列度量计算功能
"""

from dashboard.explore.metrics.kl_divergence import (
    series_to_distribution,
    kl_divergence,
    calculate_kl_divergence_series
)
from dashboard.explore.metrics.correlation import (
    calculate_time_lagged_correlation,
    find_optimal_lag
)
from dashboard.explore.metrics.dtw import (
    calculate_dtw_distance,
    calculate_dtw_path
)

__all__ = [
    # KL散度
    'series_to_distribution',
    'kl_divergence',
    'calculate_kl_divergence_series',

    # 相关性
    'calculate_time_lagged_correlation',
    'find_optimal_lag',

    # DTW
    'calculate_dtw_distance',
    'calculate_dtw_path',
]
