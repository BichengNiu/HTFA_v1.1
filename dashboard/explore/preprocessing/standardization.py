# -*- coding: utf-8 -*-
"""
时间序列数据标准化工具模块

提供统一的数据标准化接口，支持多种标准化方法，供DTW分析、领先滞后分析等模块使用。

主要功能：
1. Z-score标准化（均值为0，标准差为1）
2. Min-Max标准化（缩放到0-1范围）

设计原则：
- 单一职责：仅负责数据标准化
- DRY：避免重复实现
- KISS：简单直接，不返回元数据
- YAGNI：不提供未使用的功能
"""

import pandas as pd
import numpy as np
from typing import Tuple, Union


def standardize_array(data: np.ndarray, method: str = 'zscore') -> np.ndarray:
    """
    标准化numpy数组

    Args:
        data: 输入数据数组
        method: 标准化方法 ('zscore', 'minmax', 'none')

    Returns:
        标准化后的数据

    Raises:
        ValueError: 未知的标准化方法
    """
    VALID_METHODS = {'zscore', 'minmax', 'none'}
    if method not in VALID_METHODS:
        raise ValueError(f"未知标准化方法: {method}，有效值: {VALID_METHODS}")

    if method == 'none' or len(data) == 0:
        return data

    valid_mask = ~np.isnan(data)
    if not np.any(valid_mask):
        return data

    valid_data = data[valid_mask]

    if method == 'zscore':
        mean_val = np.mean(valid_data)
        std_val = np.std(valid_data, ddof=1)
        if std_val == 0 or np.isnan(std_val):
            return data
        return (data - mean_val) / std_val

    elif method == 'minmax':
        min_val = np.min(valid_data)
        max_val = np.max(valid_data)
        if max_val == min_val:
            return data
        return (data - min_val) / (max_val - min_val)

    return data


def standardize_series(series: pd.Series, method: str = 'zscore') -> pd.Series:
    """
    标准化pandas Series

    Args:
        series: 输入时间序列
        method: 标准化方法 ('zscore', 'minmax', 'none')

    Returns:
        标准化后的序列（失败时返回原序列副本）
    """
    if method == 'none' or series.empty or series.isna().all():
        return series.copy()

    series_clean = series.dropna()
    if len(series_clean) < 2:
        return series.copy()

    arr = series.values
    standardized_arr = standardize_array(arr, method)

    # 检查是否成功标准化（通过比较是否为同一对象）
    if standardized_arr is arr:
        return series.copy()

    return pd.Series(standardized_arr, index=series.index, name=series.name)


def standardize_series_pair(
    series1: Union[pd.Series, np.ndarray],
    series2: Union[pd.Series, np.ndarray],
    method: str = 'zscore'
) -> Tuple[np.ndarray, np.ndarray]:
    """
    标准化一对序列

    Args:
        series1: 第一个序列（Series或ndarray）
        series2: 第二个序列（Series或ndarray）
        method: 标准化方法 ('zscore', 'minmax', 'none')

    Returns:
        Tuple[标准化后的series1, 标准化后的series2]
    """
    if method == 'none':
        s1 = series1.values if isinstance(series1, pd.Series) else series1
        s2 = series2.values if isinstance(series2, pd.Series) else series2
        return s1, s2

    # 转换为numpy数组
    s1_array = series1.values if isinstance(series1, pd.Series) else series1
    s2_array = series2.values if isinstance(series2, pd.Series) else series2

    # 分别标准化
    s1_std = standardize_array(s1_array, method)
    s2_std = standardize_array(s2_array, method)

    return s1_std, s2_std
