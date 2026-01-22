# -*- coding: utf-8 -*-
"""
explore.preprocessing - 数据预处理模块

提供时间序列数据的预处理功能
"""

from dashboard.explore.preprocessing.frequency_alignment import (
    infer_series_frequency,
    resample_series_to_frequency,
    detect_and_align_frequencies,
    align_series_for_analysis,
    align_multiple_series_frequencies,
    format_alignment_report
)

from dashboard.explore.preprocessing.standardization import (
    standardize_array,
    standardize_series,
    standardize_series_pair
)

__all__ = [
    # 频率对齐
    'infer_series_frequency',
    'resample_series_to_frequency',
    'detect_and_align_frequencies',
    'align_series_for_analysis',
    'align_multiple_series_frequencies',
    'format_alignment_report',

    # 标准化
    'standardize_array',
    'standardize_series',
    'standardize_series_pair',
]
