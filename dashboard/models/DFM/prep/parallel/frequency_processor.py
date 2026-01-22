# -*- coding: utf-8 -*-
"""
频率级并行处理器

将6个频率（daily/weekly/dekad/monthly/quarterly/yearly）的处理并行化
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List, Any
import logging

logger = logging.getLogger(__name__)

# 频率等级映射（从统一常量导入）
from dashboard.models.DFM.prep.modules.config_constants import FREQ_ORDER


def _get_freq_level(freq_code: str) -> int:
    """获取频率等级"""
    return FREQ_ORDER.get(freq_code, 2)


# ========== 可序列化的顶层函数 ==========

def _process_single_frequency(
    freq_name: str,
    freq_data_serialized: Dict[str, Tuple[np.ndarray, np.ndarray]],
    original_freq: str,
    target_level: int,
    consecutive_nan_threshold: int,
    data_start_date: Optional[str],
    data_end_date: Optional[str],
    target_freq: str,
    enable_borrowing: bool
) -> Tuple[str, Optional[Tuple[np.ndarray, np.ndarray, List[str]]], Dict, List[Dict]]:
    """
    处理单个频率的数据（可序列化顶层函数）

    Args:
        freq_name: 频率名称 ('daily', 'weekly', etc.)
        freq_data_serialized: 该频率的数据字典 {变量名: (values, index)}
        original_freq: 原始频率代码 ('D', 'W', 'M', etc.)
        target_level: 目标频率等级
        consecutive_nan_threshold: 连续NaN阈值
        data_start_date: 数据开始日期
        data_end_date: 数据结束日期
        target_freq: 目标频率字符串
        enable_borrowing: 是否启用借调

    Returns:
        Tuple[str, Optional[Tuple], Dict, List[Dict]]:
            - 频率名称
            - (对齐后的values, index, columns) 或 None
            - 借调日志
            - 移除变量日志
    """
    try:
        # 在子进程中导入依赖
        from dashboard.models.DFM.prep.modules.data_aligner import DataAligner
        from dashboard.models.DFM.prep.modules.data_cleaner import DataCleaner

        if not freq_data_serialized:
            return (freq_name, None, {}, [])

        logger.info(f"  [并行] 处理{freq_name}数据...")

        # 重建DataFrame
        series_list = []
        for var_name, (values, index) in freq_data_serialized.items():
            series = pd.Series(values, index=pd.to_datetime(index), name=var_name)
            series_list.append(series)

        if not series_list:
            return (freq_name, None, {}, [])

        combined_df = pd.concat(series_list, axis=1)

        # 创建本地实例（避免共享状态）
        data_aligner = DataAligner(target_freq, enable_borrowing=enable_borrowing)
        data_cleaner = DataCleaner()
        removal_log = []
        borrowing_log = {}

        # 移除重复列
        combined_df = data_cleaner.remove_duplicate_columns(combined_df, f"[{freq_name}] ")
        removal_log.extend(data_cleaner.get_removed_variables_log())
        data_cleaner.clear_log()

        logger.info(f"    [并行-{freq_name}] 合并后形状: {combined_df.shape}")

        # 获取频率等级
        original_level = _get_freq_level(original_freq)

        # 根据频率关系选择检测时机
        if original_level <= target_level:
            # 原始频率 >= 目标频率（需要降频）：先对齐再检测
            logger.info(f"    [并行-{freq_name}] 先对齐到目标频率...")
            aligned_df, borrowing_log = data_aligner.align_by_type(
                combined_df, freq_name, data_start_date, data_end_date
            )

            logger.info(f"    [并行-{freq_name}] 再检测连续缺失值（对齐后）...")
            aligned_df = data_cleaner.handle_consecutive_nans(
                aligned_df,
                consecutive_nan_threshold,
                f"[{freq_name}对齐后] ",
                data_start_date,
                data_end_date
            )
            removal_log.extend(data_cleaner.get_removed_variables_log())
            data_cleaner.clear_log()

        else:
            # 原始频率 < 目标频率（需要升频）：先检测再对齐
            logger.info(f"    [并行-{freq_name}] 先检测连续缺失值（原始频率）...")
            cleaned_df = data_cleaner.handle_consecutive_nans(
                combined_df,
                consecutive_nan_threshold,
                f"[{freq_name}原始频率] ",
                data_start_date,
                data_end_date
            )
            removal_log.extend(data_cleaner.get_removed_variables_log())
            data_cleaner.clear_log()
            logger.info(f"    [并行-{freq_name}] 检测后形状: {cleaned_df.shape}")

            # 对齐到目标频率
            logger.info(f"    [并行-{freq_name}] 对齐到目标频率...")
            aligned_df, borrowing_log = data_aligner.align_by_type(
                cleaned_df, freq_name, data_start_date, data_end_date
            )

        logger.info(f"  [并行-{freq_name}] 完成, 形状: {aligned_df.shape}")

        # 返回可序列化的数据
        if aligned_df.empty:
            return (freq_name, None, borrowing_log, removal_log)

        return (
            freq_name,
            (aligned_df.values, aligned_df.index.values, list(aligned_df.columns)),
            borrowing_log,
            removal_log
        )

    except (ValueError, KeyError) as e:
        logger.error(f"  [并行] {freq_name}处理失败: {e}")
        raise RuntimeError(f"频率处理失败 ({freq_name}): {e}") from e
    except pd.errors.EmptyDataError as e:
        logger.error(f"  [并行] {freq_name}数据为空: {e}")
        raise ValueError(f"频率数据为空 ({freq_name}): {e}") from e


def _serialize_freq_data(freq_data: Dict[str, pd.DataFrame]) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """将频率数据序列化为可传输格式

    处理两种情况：
    1. freq_data = {'var1': Series, 'var2': Series, ...} - 直接序列化
    2. freq_data = {'combined': DataFrame} - 展开DataFrame的每一列
    """
    serialized = {}
    for var_name, df_or_series in freq_data.items():
        if isinstance(df_or_series, pd.DataFrame):
            # DataFrame: 展开每一列为独立变量
            for col in df_or_series.columns:
                series = df_or_series[col]
                serialized[col] = (series.values, series.index.values)
        elif isinstance(df_or_series, pd.Series):
            serialized[var_name] = (df_or_series.values, df_or_series.index.values)
    return serialized


def parallel_process_frequencies(
    data_by_freq: Dict[str, Dict],
    target_level: int,
    consecutive_nan_threshold: int,
    data_start_date: Optional[str],
    data_end_date: Optional[str],
    target_freq: str,
    enable_borrowing: bool,
    n_jobs: int = -1,
    backend: str = 'loky'
) -> Tuple[Dict[str, pd.DataFrame], Dict, List[Dict]]:
    """
    并行处理所有频率的数据

    Args:
        data_by_freq: 按频率分类的数据
        target_level: 目标频率等级
        consecutive_nan_threshold: 连续NaN阈值
        data_start_date: 数据开始日期
        data_end_date: 数据结束日期
        target_freq: 目标频率
        enable_borrowing: 是否启用借调
        n_jobs: 并行任务数
        backend: 并行后端

    Returns:
        Tuple[Dict, Dict, List]: (对齐后的数据, 借调日志, 移除日志)
    """
    from joblib import Parallel, delayed

    # 准备频率配置
    freq_configs = [
        ('daily', 'D'),
        ('weekly', 'W'),
        ('dekad', 'K'),  # 旬度使用独立频率代码
        ('monthly', 'M'),
        ('quarterly', 'Q'),
        ('yearly', 'Y')
    ]

    # 过滤出有数据的频率并序列化
    tasks = []
    for freq_name, original_freq in freq_configs:
        freq_data = data_by_freq.get(freq_name)
        if freq_data:
            serialized_data = _serialize_freq_data(freq_data)
            if serialized_data:
                tasks.append((freq_name, serialized_data, original_freq))

    if not tasks:
        return {}, {}, []

    logger.info(f"  并行处理 {len(tasks)} 个频率 (n_jobs={n_jobs}, backend={backend})...")

    # 并行执行
    results = Parallel(n_jobs=n_jobs, backend=backend, prefer='processes')(
        delayed(_process_single_frequency)(
            freq_name,
            freq_data,
            original_freq,
            target_level,
            consecutive_nan_threshold,
            data_start_date,
            data_end_date,
            target_freq,
            enable_borrowing
        )
        for freq_name, freq_data, original_freq in tasks
    )

    # 聚合结果
    aligned_data = {}
    all_borrowing_log = {}
    all_removal_log = []

    for freq_name, result_data, borrowing_log, removal_log in results:
        if result_data is not None:
            values, index, columns = result_data
            aligned_df = pd.DataFrame(
                values,
                index=pd.to_datetime(index),
                columns=columns
            )
            if not aligned_df.empty:
                aligned_data[freq_name] = aligned_df
        if borrowing_log:
            for key, value in borrowing_log.items():
                if key in all_borrowing_log:
                    all_borrowing_log[key].extend(value)
                else:
                    all_borrowing_log[key] = value
        all_removal_log.extend(removal_log)

    logger.info(f"  并行处理完成, 有效频率数: {len(aligned_data)}")
    return aligned_data, all_borrowing_log, all_removal_log


__all__ = [
    '_process_single_frequency',
    'parallel_process_frequencies'
]
