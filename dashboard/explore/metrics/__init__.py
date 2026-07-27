"""
explore.metrics - 度量计算模块

提供各种时间序列度量计算功能
"""

from dashboard.explore.metrics.correlation import (
    calculate_time_lagged_correlation,
    find_optimal_lag,
)
from dashboard.explore.metrics.dtw import calculate_dtw_distance, calculate_dtw_path
from dashboard.explore.metrics.kl_divergence import (
    calculate_kl_divergence_series,
    kl_divergence,
    series_to_distribution,
)

__all__ = [
    # DTW
    'calculate_dtw_distance',
    'calculate_dtw_path',
    'calculate_kl_divergence_series',
    # 相关性
    'calculate_time_lagged_correlation',
    'find_optimal_lag',
    'kl_divergence',
    # KL散度
    'series_to_distribution',
]
