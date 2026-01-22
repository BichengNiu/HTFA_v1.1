# -*- coding: utf-8 -*-
"""
ADF平稳性检验并行处理器

对每列独立执行ADF检验，支持并行加速
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional, Any, Set
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


# ========== 可序列化的顶层函数 ==========

def _adf_check_single_column(
    col_name: str,
    series_values: np.ndarray,
    series_index: np.ndarray,
    adf_p_threshold: float
) -> Tuple[str, Optional[np.ndarray], Optional[np.ndarray], Dict[str, Any]]:
    """
    对单列执行ADF平稳性检验（可序列化顶层函数）

    Args:
        col_name: 列名
        series_values: 列值（numpy数组，可序列化）
        series_index: 列索引（numpy数组，可序列化）
        adf_p_threshold: ADF检验p值阈值

    Returns:
        Tuple[str, Optional[np.ndarray], Optional[np.ndarray], Dict]:
            - 列名
            - 转换后的值数组（None表示被移除）
            - 索引数组
            - 转换日志
    """
    try:
        from statsmodels.tsa.stattools import adfuller

        # 重建Series用于计算
        series = pd.Series(series_values, index=pd.to_datetime(series_index))
        series_dropna = series.dropna()

        # 检查空数据
        if series_dropna.empty:
            return (col_name, None, None, {'status': 'skipped_empty'})

        # 检查常量数据
        if series_dropna.nunique() == 1:
            return (col_name, None, None, {'status': 'skipped_constant'})

        # Level ADF检验
        adf_result_level = adfuller(series_dropna)
        if adf_result_level[1] is None or pd.isna(adf_result_level[1]):
            raise ValueError(f"ADF检验返回无效p值: {adf_result_level[1]}")
        original_pval = float(adf_result_level[1])

        if original_pval < adf_p_threshold:
            # Level已经平稳
            return (col_name, series_values, series_index, {
                'status': 'level',
                'original_pval': original_pval
            })

        # 尝试转换
        if (series_dropna > 0).all():
            series_transformed = np.log(series).diff(1)
            transform_type = 'log_diff'
        else:
            series_transformed = series.diff(1)
            transform_type = 'diff'

        series_transformed_dropna = series_transformed.dropna()

        # 检查转换后的序列
        if series_transformed_dropna.empty:
            return (col_name, None, None, {
                'status': f'skipped_{transform_type}_empty',
                'original_pval': original_pval
            })

        if series_transformed_dropna.nunique() == 1:
            return (col_name, None, None, {
                'status': f'skipped_{transform_type}_constant',
                'original_pval': original_pval
            })

        # 对转换后的序列进行ADF检验
        try:
            adf_result_transformed = adfuller(series_transformed_dropna)
            diff_pval = float(adf_result_transformed[1])

            if diff_pval < adf_p_threshold:
                return (col_name, series_transformed.values, series_index, {
                    'status': transform_type,
                    'original_pval': original_pval,
                    'diff_pval': diff_pval
                })
            else:
                return (col_name, series_transformed.values, series_index, {
                    'status': f'{transform_type}_still_nonstat',
                    'original_pval': original_pval,
                    'diff_pval': diff_pval
                })
        except Exception as e:
            return (col_name, series_transformed.values, series_index, {
                'status': f'{transform_type}_test_error',
                'original_pval': original_pval,
                'error': str(e)
            })

    except (ValueError, np.linalg.LinAlgError) as e:
        logger.error(f"[ADF并行] 列 '{col_name}' 检验失败 (数值错误): {e}")
        raise RuntimeError(f"ADF检验失败 ({col_name}): {e}") from e
    except ImportError as e:
        logger.error(f"[ADF并行] statsmodels导入失败: {e}")
        raise


def parallel_adf_check(
    df: pd.DataFrame,
    skip_cols: Optional[Set[str]] = None,
    adf_p_threshold: float = 0.05,
    n_jobs: int = -1,
    backend: str = 'loky'
) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, List[str]]]:
    """
    并行执行ADF平稳性检验

    Args:
        df: 输入DataFrame
        skip_cols: 跳过的列名集合
        adf_p_threshold: p值阈值
        n_jobs: 并行任务数
        backend: 并行后端

    Returns:
        Tuple[pd.DataFrame, Dict, Dict]:
            - 转换后的DataFrame
            - 转换日志字典
            - 移除列信息字典
    """
    from joblib import Parallel, delayed
    from dashboard.models.DFM.utils.text_utils import normalize_text

    logger.info(f"\n--- [ADF并行] 开始检查平稳性 (p<{adf_p_threshold}, n_jobs={n_jobs}) ---")

    # 标准化跳过列表
    skip_cols_normalized = set()
    if skip_cols:
        skip_cols_normalized = {normalize_text(c) for c in skip_cols}
        logger.info(f"    跳过列�� (首5项): {list(skip_cols_normalized)[:5]}")

    # 分离跳过的列和需要处理的列
    tasks = []
    skipped_data = {}  # 存储跳过的列数据

    for col in df.columns:
        col_normalized = normalize_text(col)
        if col_normalized in skip_cols_normalized:
            # 跳过列直接保留
            skipped_data[col] = df[col].copy()
            continue

        # 提取可序列化数据
        series = df[col]
        tasks.append((col, series.values, series.index.values))

    if not tasks:
        logger.info("    所有列都在跳过列表中，直接返回")
        transform_log = {col: {'status': 'skipped_by_request'} for col in df.columns}
        return df.copy(), transform_log, {}

    logger.info(f"    并行处理 {len(tasks)} 列 (跳过 {len(skipped_data)} 列)...")

    # 并行执行
    results = Parallel(n_jobs=n_jobs, backend=backend, prefer='processes')(
        delayed(_adf_check_single_column)(col, values, index, adf_p_threshold)
        for col, values, index in tasks
    )

    # 聚合结果
    transformed_data = pd.DataFrame(index=df.index)
    transform_log = {}
    removed_cols_info = defaultdict(list)

    # 添加跳过的列
    for col, series in skipped_data.items():
        transformed_data[col] = series
        transform_log[col] = {'status': 'skipped_by_request'}
        logger.info(f"    - {col}: 根据请求跳过平稳性检查")

    # 添加处理后的列
    for col_name, values, index, log in results:
        transform_log[col_name] = log

        if values is not None:
            # 重建Series
            result_series = pd.Series(values, index=pd.to_datetime(index), name=col_name)
            # 重新索引到原始索引
            transformed_data[col_name] = result_series.reindex(df.index)

            status = log.get('status', 'unknown')
            if 'level' in status:
                logger.info(f"    - {col_name}: Level 平稳 (p={log.get('original_pval', 'N/A'):.3f})")
            elif 'still_nonstat' in status:
                logger.info(f"    - {col_name}: 差分后仍不平稳 (p={log.get('diff_pval', 'N/A'):.3f})")
            else:
                logger.info(f"    - {col_name}: {status}")
        else:
            status = log.get('status', 'unknown')
            removed_cols_info[status].append(col_name)
            logger.info(f"    - {col_name}: 已移除 ({status})")

    # 统计
    total_removed = sum(len(v) for v in removed_cols_info.values())
    logger.info(f"--- [ADF并行] 完成. 输出形状: {transformed_data.shape}, 移除: {total_removed} ---")

    return transformed_data, transform_log, dict(removed_cols_info)


__all__ = [
    '_adf_check_single_column',
    'parallel_adf_check'
]
