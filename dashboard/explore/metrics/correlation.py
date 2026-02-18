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


def _prepare_correlation_inputs(series1, series2):
    """准备相关性计算的输入数组

    Returns:
        tuple: (arr1, arr2) numpy数组，如果输入无效返回 (None, None)
    """
    if not isinstance(series1, pd.Series):
        series1 = pd.Series(series1)
    if not isinstance(series2, pd.Series):
        series2 = pd.Series(series2)

    try:
        arr1 = series1.astype(float).values
        arr2 = series2.astype(float).values
    except Exception as e:
        logger.error(f"序列转换失败: {e}")
        return None, None

    if len(arr1) == 0 or len(arr2) == 0:
        return None, None

    if np.all(np.isnan(arr1)) or np.all(np.isnan(arr2)):
        return None, None

    return arr1, arr2


def _empty_correlogram(max_lags):
    """返回空的相关图 DataFrame"""
    return pd.DataFrame({
        'Lag': range(-max_lags, max_lags + 1),
        'Correlation': [np.nan] * (2 * max_lags + 1)
    })


def _correlation_loop(arr1, arr2, max_lags, corr_func):
    """通用相关性循环

    Args:
        arr1, arr2: numpy 数组
        max_lags: 最大滞后阶数
        corr_func: 接受 (slice1, slice2) 返回 float 的相关系数计算函数

    Returns:
        DataFrame: 包含 'Lag' 和 'Correlation' 两列
    """
    lags = []
    correlations = []

    for lag in range(-max_lags, max_lags + 1):
        lags.append(lag)
        slice1, slice2 = get_lagged_slices(arr1, arr2, lag)

        if slice1 is None or slice2 is None:
            correlations.append(np.nan)
            continue

        correlations.append(corr_func(slice1, slice2))

    return pd.DataFrame({'Lag': lags, 'Correlation': correlations})


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
    """计算时差相关性（标准Pandas版本）"""
    arr1, arr2 = _prepare_correlation_inputs(series1, series2)
    if arr1 is None:
        return _empty_correlogram(max_lags)

    def _pandas_corr(slice1, slice2):
        s1 = pd.Series(slice1)
        s2 = pd.Series(slice2)
        return _calculate_correlation(s1, s2)

    return _correlation_loop(arr1, arr2, max_lags, _pandas_corr)


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
    """计算时差相关性（numpy优化版本，性能提升50-70%）"""
    arr1, arr2 = _prepare_correlation_inputs(series1, series2)
    if arr1 is None:
        return _empty_correlogram(max_lags)

    def _numpy_corr(s1_view, s2_view):
        if len(s1_view) < MIN_SAMPLES_CORRELATION or len(s2_view) < MIN_SAMPLES_CORRELATION:
            return np.nan

        valid_mask = ~(np.isnan(s1_view) | np.isnan(s2_view))
        if np.sum(valid_mask) < MIN_SAMPLES_CORRELATION:
            return np.nan

        s1_valid = s1_view[valid_mask]
        s2_valid = s2_view[valid_mask]

        if len(np.unique(s1_valid)) < 2 or len(np.unique(s2_valid)) < 2:
            return np.nan

        try:
            return np.corrcoef(s1_valid, s2_valid)[0, 1]
        except Exception as e:
            logger.debug(f"相关系数计算失败: {e}")
            return np.nan

    return _correlation_loop(arr1, arr2, max_lags, _numpy_corr)
