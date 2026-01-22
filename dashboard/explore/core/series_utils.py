# -*- coding: utf-8 -*-
"""
序列处理工具模块

提供时间序列的通用处理功能，包括清洗、对齐、时间列识别等
"""

import logging
from typing import Optional, Tuple, List
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def clean_numeric_series(
    series: pd.Series,
    remove_na: bool = True,
    convert_to_numeric: bool = True
) -> pd.Series:
    """
    清洗数值序列

    Args:
        series: 输入序列
        remove_na: 是否移除NaN值
        convert_to_numeric: 是否转换为数值类型

    Returns:
        清洗后的序列
    """
    result = series.copy()

    # 转换为数值类型
    if convert_to_numeric and not pd.api.types.is_numeric_dtype(result):
        result = pd.to_numeric(result, errors='coerce')
        logger.debug(f"序列 '{series.name}' 已转换为数值类型")

    # 移除NaN
    if remove_na:
        n_before = len(result)
        result = result.dropna()
        n_after = len(result)
        if n_before != n_after:
            logger.debug(f"序列 '{series.name}' 移除了 {n_before - n_after} 个NaN值")

    return result


def clean_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    清理DataFrame列名中的首尾空格

    Args:
        df: 输入DataFrame

    Returns:
        列名已清理的DataFrame（原地修改）
    """
    if hasattr(df.columns, 'str'):
        df.columns = df.columns.str.strip()
    return df


def identify_time_column(df: pd.DataFrame, exclude_columns: Optional[List[str]] = None) -> Optional[str]:
    """
    智能识别DataFrame中的时间列

    统一了stationarity_backend.py和frequency_alignment.py中的重复逻辑

    Args:
        df: 输入DataFrame
        exclude_columns: 要排除的列名列表（通常是数据列）

    Returns:
        时间列名称，如果未找到则返回None
    """
    exclude_columns = exclude_columns or []

    # 方法1：检查索引是否为DatetimeIndex
    if isinstance(df.index, pd.DatetimeIndex):
        index_name = df.index.name if df.index.name else "时间索引"
        logger.info(f"识别到DatetimeIndex: '{index_name}'")
        return index_name

    # 方法2：按数据类型识别datetime列
    datetime_cols = df.select_dtypes(include=['datetime', 'datetime64']).columns.tolist()
    datetime_cols = [col for col in datetime_cols if col not in exclude_columns]

    if len(datetime_cols) == 1:
        logger.info(f"识别到datetime类型列: '{datetime_cols[0]}'")
        return datetime_cols[0]
    elif len(datetime_cols) > 1:
        logger.warning(f"发现多个datetime列: {datetime_cols}，无法自动确定")
        return None

    # 方法3：尝试将第一列转换为datetime
    if len(df.columns) > 0:
        first_col = df.columns[0]
        if first_col not in exclude_columns:
            try:
                # 尝试转换前几个值
                sample_data = df[first_col].dropna().head(5)
                if len(sample_data) > 0:
                    time_series = pd.to_datetime(sample_data, errors='coerce')
                    if not time_series.isnull().all():
                        logger.info(f"第一列 '{first_col}' 可转换为datetime类型")
                        return first_col
            except Exception as e:
                logger.debug(f"第一列 '{first_col}' 无法转换为datetime: {e}")

    logger.warning("未能识别到时间列")
    return None


def prepare_time_index(
    df: pd.DataFrame,
    time_column: Optional[str] = None,
    set_as_index: bool = True,
    keep_column: bool = True
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    准备时间索引

    Args:
        df: 输入DataFrame
        time_column: 指定的时间列名（None则自动识别）
        set_as_index: 是否设置为索引
        keep_column: 是否保留原列

    Returns:
        Tuple[处理后的DataFrame, 时间列名]
    """
    df_work = df.copy()

    # 如果已经是DatetimeIndex，直接返回
    if isinstance(df_work.index, pd.DatetimeIndex):
        index_name = df_work.index.name if df_work.index.name else "时间索引"
        return df_work, index_name

    # 识别或验证时间列
    if time_column is None:
        time_column = identify_time_column(df_work)

    if time_column is None:
        logger.warning("无法找到有效的时间列")
        return df_work, None

    # 如果时间列不在DataFrame中，可能是索引
    if time_column not in df_work.columns and time_column == (df_work.index.name or "时间索引"):
        return df_work, time_column

    # 转换时间列为datetime类型
    try:
        df_work[time_column] = pd.to_datetime(df_work[time_column], errors='coerce')
        logger.info(f"时间列 '{time_column}' 已转换为datetime类型")
    except Exception as e:
        logger.error(f"转换时间列失败: {e}")
        return df_work, None

    # 设置为索引
    if set_as_index:
        try:
            df_work = df_work.set_index(time_column, drop=not keep_column)
            logger.info(f"时间列 '{time_column}' 已设置为索引 (keep_column={keep_column})")
        except Exception as e:
            logger.error(f"设置时间索引失败: {e}")

    return df_work, time_column


def get_lagged_slices(
    data1: np.ndarray,
    data2: np.ndarray,
    lag: int
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    获取两个数组在给定滞后下的切片（统一实现，消除重复）

    这个函数统一了correlation.py和lead_lag.py中重复的切片逻辑，
    使用numpy的view操作实现零拷贝切片，提高性能。

    Args:
        data1: 第一个数组（参考序列）
        data2: 第二个数组（待滞后序列）
        lag: 滞后值
             - lag=0: 无偏移
             - lag>0: data2领先data1（data2向前移动）
             - lag<0: data1领先data2（data1向前移动）

    Returns:
        Tuple[data1的切片view, data2的切片view]
        如果切片后长度不足，返回(None, None)

    示例:
        data1 = [1, 2, 3, 4, 5]
        data2 = [a, b, c, d, e]

        lag=0:  [1,2,3,4,5] vs [a,b,c,d,e]
        lag=1:  [2,3,4,5] vs [a,b,c,d]  (data2领先)
        lag=-1: [1,2,3,4] vs [b,c,d,e]  (data1领先)
    """
    n1 = len(data1)
    n2 = len(data2)

    if n1 == 0 or n2 == 0:
        return None, None

    # 边界检查：滞后值不能等于或超过序列长度
    if abs(lag) >= min(n1, n2):
        logger.debug(f"滞后值 {lag} 超过最小序列长度 {min(n1, n2)}，无法切片")
        return None, None

    if lag == 0:
        # 无偏移，取较短长度
        min_len = min(n1, n2)
        return data1[:min_len], data2[:min_len]

    elif lag > 0:
        # data2领先：data1去掉开头lag个，data2去掉末尾lag个
        if n1 <= lag or n2 <= lag:
            return None, None

        slice1 = data1[lag:]
        slice2 = data2[:-lag] if lag < n2 else np.array([])

    else:  # lag < 0
        # data1领先：data1去掉末尾abs(lag)个，data2去掉开头abs(lag)个
        abs_lag = abs(lag)
        if n1 <= abs_lag or n2 <= abs_lag:
            return None, None

        slice1 = data1[:-abs_lag] if abs_lag < n1 else np.array([])
        slice2 = data2[abs_lag:]

    # 对齐长度（取较短的）
    if len(slice1) == 0 or len(slice2) == 0:
        return None, None

    min_len = min(len(slice1), len(slice2))
    if min_len == 0:
        return None, None

    return slice1[:min_len], slice2[:min_len]


def get_lagged_series_slices(
    series1: pd.Series,
    series2: pd.Series,
    lag: int
) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
    """
    获取两个pandas Series在给定滞后下的切片

    这是get_lagged_slices的Series版本包装器

    Args:
        series1: 第一个序列
        series2: 第二个序列
        lag: 滞后值

    Returns:
        Tuple[series1的切片, series2的切片]
    """
    # 转换为numpy数组
    arr1 = series1.values if isinstance(series1, pd.Series) else series1
    arr2 = series2.values if isinstance(series2, pd.Series) else series2

    # 使用统一的切片函数
    slice1, slice2 = get_lagged_slices(arr1, arr2, lag)

    if slice1 is None or slice2 is None:
        return None, None

    # 转换回Series（保留名称）
    s1_result = pd.Series(slice1, name=series1.name if hasattr(series1, 'name') else None)
    s2_result = pd.Series(slice2, name=series2.name if hasattr(series2, 'name') else None)

    return s1_result, s2_result
