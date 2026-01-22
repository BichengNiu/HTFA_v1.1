# -*- coding: utf-8 -*-
"""
缺失值检测并行处理器

对每列独立检测连续NaN值，支持并行加速
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


# ========== 可序列化的顶层函数 ==========

def _detect_consecutive_nans_single_column(
    col_name: str,
    series_values: np.ndarray,
    series_index: np.ndarray,
    threshold: int,
    start_date: Optional[str],
    end_date: Optional[str]
) -> Tuple[str, int, Optional[str], Optional[str], Dict[str, Any]]:
    """
    检测单列的连续NaN值（可序列化顶层函数）

    Args:
        col_name: 列名
        series_values: 列值（numpy数组）
        series_index: 列索引（numpy数组）
        threshold: 连续NaN阈值
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        Tuple[str, int, Optional[str], Optional[str], Dict]:
            - 列名
            - 最大连续NaN数
            - NaN开始日期
            - NaN结束日期
            - 详细信息字典
    """
    try:
        # 重建Series
        series = pd.Series(series_values, index=pd.to_datetime(series_index), name=col_name)

        # 应用时间范围筛选
        if start_date or end_date:
            if start_date:
                series = series[series.index >= pd.to_datetime(start_date)]
            if end_date:
                series = series[series.index <= pd.to_datetime(end_date)]

        if series.empty:
            return (col_name, 0, None, None, {'status': 'empty_after_filter'})

        # 找到第一个有效值
        first_valid_idx = series.first_valid_index()
        if first_valid_idx is None:
            # 全部为NaN
            return (col_name, len(series), str(series.index[0]), str(series.index[-1]),
                   {'status': 'all_nan'})

        # 从第一个有效值开始分析
        series_after_first_valid = series.loc[first_valid_idx:]
        is_na = series_after_first_valid.isna()

        if not is_na.any():
            return (col_name, 0, None, None, {'status': 'no_nan'})

        # 计算连续NaN块
        na_blocks = is_na.ne(is_na.shift()).cumsum()[is_na]

        if na_blocks.empty:
            return (col_name, 0, None, None, {'status': 'no_nan_blocks'})

        block_counts = na_blocks.value_counts()
        max_consecutive_nan = int(block_counts.max())
        max_block_id = block_counts.idxmax()

        # 找到该块的起止日期
        max_block_indices = na_blocks[na_blocks == max_block_id].index
        nan_start = str(max_block_indices[0]) if len(max_block_indices) > 0 else None
        nan_end = str(max_block_indices[-1]) if len(max_block_indices) > 0 else None

        # 计算统计信息
        total_points = len(series)
        missing_points = int(series.isnull().sum())
        missing_ratio = round(missing_points / total_points * 100, 2) if total_points > 0 else 0

        return (col_name, max_consecutive_nan, nan_start, nan_end, {
            'status': 'checked',
            'total_points': total_points,
            'missing_points': missing_points,
            'missing_ratio': missing_ratio
        })

    except Exception as e:
        logger.error(f"[缺失值并行] 列 '{col_name}' 检测失败: {e}")
        return (col_name, 0, None, None, {'status': 'error', 'error': str(e)})


def parallel_detect_consecutive_nans(
    df: pd.DataFrame,
    threshold: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    log_prefix: str = "",
    n_jobs: int = -1,
    backend: str = 'loky'
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    并行检测所有列的连续NaN值

    Args:
        df: 输入DataFrame
        threshold: 连续NaN阈值
        start_date: 开始日期
        end_date: 结束日期
        log_prefix: 日志前缀
        n_jobs: 并行任务数
        backend: 并行后端

    Returns:
        Tuple[pd.DataFrame, List[Dict]]: (清理后的数据, 移除变量日志)
    """
    from joblib import Parallel, delayed

    if df.empty or threshold is None or threshold <= 0:
        return df, []

    # 首先处理重复列名
    if df.columns.duplicated().any():
        logger.info(f"  {log_prefix}警告: 检测到重复列名，正在去重...")
        df = df.loc[:, ~df.columns.duplicated(keep='first')]

    logger.info(f"  {log_prefix}[缺失值并行] 检查连续NaN (阈值>={threshold}, n_jobs={n_jobs})...")
    if start_date or end_date:
        logger.info(f"  {log_prefix}时间范围: {start_date} 到 {end_date}")

    # 准备任务
    tasks = [
        (col, df[col].values, df.index.values)
        for col in df.columns
    ]

    # 并行执行
    results = Parallel(n_jobs=n_jobs, backend=backend, prefer='processes')(
        delayed(_detect_consecutive_nans_single_column)(
            col, values, index, threshold, start_date, end_date
        )
        for col, values, index in tasks
    )

    # 聚合结果
    cols_to_remove = []
    removal_log = []

    for col_name, max_nan, nan_start, nan_end, info in results:
        if max_nan >= threshold:
            cols_to_remove.append(col_name)
            removal_log.append({
                'Variable': col_name,
                'Reason': f'{log_prefix}consecutive_nan_parallel',
                'Details': {
                    'max_consecutive_nan': max_nan,
                    'nan_start_date': nan_start,
                    'nan_end_date': nan_end,
                    'threshold': threshold,
                    **info
                }
            })
            logger.info(
                f"    {log_prefix}标记移除: '{col_name}' "
                f"(最大连续NaN: {max_nan} >= {threshold})"
            )

    # 移除超标列
    if cols_to_remove:
        df_cleaned = df.drop(columns=cols_to_remove)
        logger.info(f"  {log_prefix}[缺失值并行] 移除 {len(cols_to_remove)} 列, 剩余形状: {df_cleaned.shape}")
        return df_cleaned, removal_log
    else:
        logger.info(f"  {log_prefix}[缺失值并行] 所有列连续NaN低于阈值")
        return df, []


__all__ = [
    '_detect_consecutive_nans_single_column',
    'parallel_detect_consecutive_nans'
]
