# -*- coding: utf-8 -*-
"""
相关性计算模块

从time_lag_corr_backend.py中提取并优化的时差相关性计算功能
"""

import logging
from typing import Tuple, Optional
import pandas as pd
import numpy as np

from dashboard.explore.core.constants import MIN_SAMPLES_CORRELATION
from dashboard.explore.core.series_utils import get_lagged_slices

logger = logging.getLogger(__name__)


def calculate_time_lagged_correlation(
    series1: pd.Series,
    series2: pd.Series,
    max_lags: int,
    use_optimized: bool = True
) -> pd.DataFrame:
    """
    计算两个时间序列之间的时差相关性（统一接口）

    性能说明：
    - numpy优化版本（use_optimized=True，默认）：使用numpy.corrcoef，性能最优
    - pandas标准版本（use_optimized=False）：使用pandas.Series.corr，兼容性好

    重构说明：
    - 两个版本现在都使用统一的get_lagged_slices函数（消除代码重复）
    - 推荐使用numpy优化版本以获得更好的性能

    Args:
        series1: 第一个时间序列
        series2: 第二个时间序列
        max_lags: 最大滞后/超前阶数
        use_optimized: 是否使用numpy优化版本（默认True，推荐）

    Returns:
        DataFrame: 包含'Lag'和'Correlation'两列
                   Lag从-max_lags到+max_lags
                   正滞后表示series2领先series1
    """
    if use_optimized:
        return _calculate_time_lagged_correlation_numpy(series1, series2, max_lags)
    else:
        return _calculate_time_lagged_correlation_pandas(series1, series2, max_lags)


def _calculate_time_lagged_correlation_pandas(
    series1: pd.Series,
    series2: pd.Series,
    max_lags: int
) -> pd.DataFrame:
    """
    计算两个时间序列之间的时差相关性（标准Pandas版本）

    重构说明：使用统一的get_lagged_slices函数，消除代码重复

    Args:
        series1: 第一个时间序列
        series2: 第二个时间序列
        max_lags: 最大滞后/超前阶数

    Returns:
        DataFrame: 包含'Lag'和'Correlation'两列
    """
    # 确保输入为Series
    if not isinstance(series1, pd.Series):
        series1 = pd.Series(series1)
    if not isinstance(series2, pd.Series):
        series2 = pd.Series(series2)

    # 转换为浮点数并处理空值
    series1 = series1.astype(float)
    series2 = series2.astype(float)

    # 空数据检查
    if series1.empty or series2.empty or series1.isnull().all() or series2.isnull().all():
        lags_range = range(-max_lags, max_lags + 1)
        correlations_val = [np.nan] * len(lags_range)
        return pd.DataFrame({'Lag': lags_range, 'Correlation': correlations_val})

    # 转换为numpy数组以使用统一的切片函数
    arr1 = series1.values
    arr2 = series2.values

    if len(arr1) == 0 or len(arr2) == 0:
        lags_range = range(-max_lags, max_lags + 1)
        correlations_val = [np.nan] * len(lags_range)
        return pd.DataFrame({'Lag': lags_range, 'Correlation': correlations_val})

    lags = []
    correlations = []

    for lag in range(-max_lags, max_lags + 1):
        lags.append(lag)

        # 使用统一的切片函数（消除重复代码）
        slice1, slice2 = get_lagged_slices(arr1, arr2, lag)

        if slice1 is None or slice2 is None:
            correlations.append(np.nan)
            continue

        # 转换回Series进行相关性计算
        s1_slice = pd.Series(slice1)
        s2_slice = pd.Series(slice2)

        # 计算相关系数
        corr_val = _calculate_correlation(s1_slice, s2_slice)
        correlations.append(corr_val)

    return pd.DataFrame({'Lag': lags, 'Correlation': correlations})


def _calculate_correlation(s1: pd.Series, s2: pd.Series) -> float:
    """
    计算两个序列的相关系数

    Args:
        s1: 第一个序列
        s2: 第二个序列

    Returns:
        相关系数（如果无法计算则返回NaN）
    """
    if len(s1) < MIN_SAMPLES_CORRELATION or len(s2) < MIN_SAMPLES_CORRELATION:
        return np.nan

    if s1.isnull().all() or s2.isnull().all():
        return np.nan

    # 重置索引以确保corr正确工作
    s1_reset = s1.reset_index(drop=True)
    s2_reset = s2.reset_index(drop=True)

    # 检查方差
    if s1_reset.nunique(dropna=True) < 2 or s2_reset.nunique(dropna=True) < 2:
        return np.nan

    try:
        correlation = s1_reset.corr(s2_reset)
        return correlation
    except Exception as e:
        logger.warning(f"相关系数计算失败: {e}")
        return np.nan


def find_optimal_lag(
    correlogram_df: pd.DataFrame,
    lag_range: str = 'all',
    max_lag_range: Optional[int] = None
) -> Tuple[Optional[int], Optional[float]]:
    """
    从相关图中找到最优滞后阶数

    Args:
        correlogram_df: 相关图DataFrame（包含Lag和Correlation列）
        lag_range: 滞后范围选择
                   'all' - 所有滞后
                   'positive' - 仅正滞后（series2领先）
                   'negative' - 仅负滞后（series1领先）
        max_lag_range: 最大滞后范围限制，如果设置，只在[-max_lag_range, max_lag_range]范围内搜索

    Returns:
        Tuple[最优滞后阶数, 对应的相关系数]
    """
    if correlogram_df.empty or 'Correlation' not in correlogram_df.columns:
        return None, None

    if not correlogram_df['Correlation'].notna().any():
        return None, None

    # 根据范围筛选（明确使用.copy()避免SettingWithCopyWarning）
    if lag_range == 'positive':
        filtered_df = correlogram_df[correlogram_df['Lag'] > 0].copy()
    elif lag_range == 'negative':
        filtered_df = correlogram_df[correlogram_df['Lag'] < 0].copy()
    else:
        filtered_df = correlogram_df.copy()

    # 应用最大滞后范围限制
    if max_lag_range is not None:
        filtered_df = filtered_df[
            (filtered_df['Lag'] >= -max_lag_range) &
            (filtered_df['Lag'] <= max_lag_range)
        ].copy()

    if filtered_df.empty or not filtered_df['Correlation'].notna().any():
        return None, None

    # 找到绝对值最大的相关系数
    abs_corr = filtered_df['Correlation'].abs()
    optimal_idx = abs_corr.idxmax()

    optimal_lag = filtered_df.loc[optimal_idx, 'Lag']
    optimal_corr = filtered_df.loc[optimal_idx, 'Correlation']

    return int(optimal_lag), float(optimal_corr)


def _calculate_time_lagged_correlation_numpy(
    series1: pd.Series,
    series2: pd.Series,
    max_lags: int
) -> pd.DataFrame:
    """
    计算两个时间序列之间的时差相关性（numpy优化版本）

    性能优化要点：
    - 预先转换为numpy数组（避免重复转换）
    - 使用numpy切片（零拷贝view）
    - 批量计算（减少函数调用开销）

    预期性能提升：50-70%

    Args:
        series1: 第一个时间序列
        series2: 第二个时间序列
        max_lags: 最大滞后/超前阶数

    Returns:
        DataFrame: 包含'Lag'和'Correlation'两列
    """
    # 1. 预处理和验证
    if not isinstance(series1, pd.Series):
        series1 = pd.Series(series1)
    if not isinstance(series2, pd.Series):
        series2 = pd.Series(series2)

    # 转换为numpy数组
    try:
        s1_arr = series1.astype(float).values
        s2_arr = series2.astype(float).values
    except Exception as e:
        logger.error(f"序列转换失败: {e}")
        return pd.DataFrame({
            'Lag': range(-max_lags, max_lags + 1),
            'Correlation': [np.nan] * (2 * max_lags + 1)
        })

    # 空数据检查
    if len(s1_arr) == 0 or len(s2_arr) == 0:
        return pd.DataFrame({
            'Lag': range(-max_lags, max_lags + 1),
            'Correlation': [np.nan] * (2 * max_lags + 1)
        })

    # 2. 批量计算相关系数（使用统一的切片函数）
    lags = []
    correlations = []

    for lag in range(-max_lags, max_lags + 1):
        lags.append(lag)

        # 使用统一的切片函数（零拷贝view）
        s1_view, s2_view = get_lagged_slices(s1_arr, s2_arr, lag)

        if s1_view is None or s2_view is None:
            correlations.append(np.nan)
            continue

        # 检查最小样本数
        if len(s1_view) < MIN_SAMPLES_CORRELATION or len(s2_view) < MIN_SAMPLES_CORRELATION:
            correlations.append(np.nan)
            continue

        # 移除NaN
        valid_mask = ~(np.isnan(s1_view) | np.isnan(s2_view))
        if np.sum(valid_mask) < MIN_SAMPLES_CORRELATION:
            correlations.append(np.nan)
            continue

        s1_valid = s1_view[valid_mask]
        s2_valid = s2_view[valid_mask]

        # 检查方差
        if len(np.unique(s1_valid)) < 2 or len(np.unique(s2_valid)) < 2:
            correlations.append(np.nan)
            continue

        # 使用numpy计算相关系数（比pandas.corr快）
        try:
            corr_matrix = np.corrcoef(s1_valid, s2_valid)
            correlation = corr_matrix[0, 1]
            correlations.append(correlation)
        except Exception as e:
            logger.debug(f"相关系数计算失败 (lag={lag}): {e}")
            correlations.append(np.nan)

    return pd.DataFrame({'Lag': lags, 'Correlation': correlations})
