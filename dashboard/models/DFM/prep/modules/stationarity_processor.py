"""
平稳性处理模块

负责时间序列数据的平稳性检查和转换
包括ADF检验、差分转换、对数差分等功能
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Set, Any
from collections import defaultdict, Counter
from statsmodels.tsa.stattools import adfuller

from dashboard.models.DFM.utils.text_utils import normalize_text

logger = logging.getLogger(__name__)

# ADF检验默认p值阈值
ADF_P_THRESHOLD = 0.05

def ensure_stationarity(
    df: pd.DataFrame,
    skip_cols: Optional[Set] = None,
    adf_p_threshold: float = 0.05
) -> Tuple[pd.DataFrame, Dict, Dict]:
    """
    检查并转换DataFrame中的变量以达到平稳性
    
    处理逻辑:
    1. 对df中的每一列进行处理 (除非在skip_cols中指定)
    2. 进行ADF检验 (Level)
    3. 如果平稳 (p < adf_p_threshold)，保留level
    4. 如果不平稳，计算一阶差分，再次检验
    5. 如果差分后平稳，使用差分序列
    6. 如果差分后仍不平稳，仍使用差分序列，但标记状态
    7. 移除原始为空/常量的列，或差分后为空/常量的列
    8. 被跳过的列直接保留原始值
    
    Args:
        df: 输入的DataFrame
        skip_cols: 需要跳过检查的列名集合
        adf_p_threshold: ADF检验的p值阈值
        
    Returns:
        Tuple[pd.DataFrame, Dict, Dict]: (转换后的数据, 转换日志, 移除列信息)
    """
    logger.info("[Stationarity Check] 开始检查和转换平稳性 (ADF p<%s)", adf_p_threshold)

    transformed_data = pd.DataFrame(index=df.index)
    transform_log = {}
    removed_cols_info = defaultdict(list)

    # 标准化跳过列表以便可靠匹配
    skip_cols_normalized = set()
    if skip_cols:
        skip_cols_normalized = {normalize_text(c) for c in skip_cols}
        logger.debug("[Stationarity Check] 标准化后的跳过列表 (首5项): %s", list(skip_cols_normalized)[:5])

    for col in df.columns:
        # 检查是否在跳过列表中
        col_normalized = normalize_text(col)
        if col_normalized in skip_cols_normalized:
            transformed_data[col] = df[col].copy()
            transform_log[col] = {'status': 'skipped_by_request'}
            logger.debug("    - %s: 根据请求跳过平稳性检查 (匹配到规范化名称 '%s')", col, col_normalized)
            continue

        series = df[col]
        series_dropna = series.dropna()

        # 检查空数据
        if series_dropna.empty:
            transform_log[col] = {'status': 'skipped_empty'}
            removed_cols_info['skipped_empty'].append(col)
            logger.debug("    - %s: 数据为空或全为 NaN，已移除", col)
            continue

        # 检查常量数据
        if series_dropna.nunique() == 1:
            transform_log[col] = {'status': 'skipped_constant'}
            removed_cols_info['skipped_constant'].append(col)
            logger.debug("    - %s: 列为常量，已移除", col)
            continue

        # 进行平稳性检查和转换
        original_pval = np.nan
        diff_pval = np.nan

        # Level ADF检验
        adf_result_level = adfuller(series_dropna)
        original_pval = adf_result_level[1]

        if original_pval < adf_p_threshold:
            # Level已经平稳
            transformed_data[col] = series
            transform_log[col] = {'status': 'level', 'original_pval': original_pval}
        else:
            # Level不平稳，尝试转换
            series_orig = series
            series_transformed = None
            transform_type = 'diff'  # 默认为普通差分

            # 检查是否可以进行对数差分（所有值为正）
            if (series_dropna > 0).all():
                series_transformed = np.log(series_orig).diff(1)
                transform_type = 'log_diff'
            else:
                # 包含非正值，使用普通一阶差分
                series_transformed = series_orig.diff(1)
                transform_type = 'diff'

            series_transformed_dropna = series_transformed.dropna()

            # 检查转换后的序列
            if series_transformed_dropna.empty:
                transform_log[col] = {'status': f'skipped_{transform_type}_empty', 'original_pval': original_pval}
                removed_cols_info[f'skipped_{transform_type}_empty'].append(col)
                logger.debug("    - %s: %s 后为空，已移除", col, transform_type.capitalize())
                continue

            if series_transformed_dropna.nunique() == 1:
                transform_log[col] = {'status': f'skipped_{transform_type}_constant', 'original_pval': original_pval}
                removed_cols_info[f'skipped_{transform_type}_constant'].append(col)
                logger.debug("    - %s: %s 后为常量，已移除", col, transform_type.capitalize())
                continue

            # 对转换后的序列进行ADF检验
            adf_result_transformed = adfuller(series_transformed_dropna)
            diff_pval = adf_result_transformed[1]

            transformed_data[col] = series_transformed

            if diff_pval < adf_p_threshold:
                transform_log[col] = {'status': transform_type, 'original_pval': original_pval, 'diff_pval': diff_pval}
                logger.debug("    - %s: %s 后平稳 (p=%.3f), 使用 %s", col, transform_type.capitalize(), diff_pval, transform_type.capitalize())
            else:
                transform_log[col] = {'status': f'{transform_type}_still_nonstat', 'original_pval': original_pval, 'diff_pval': diff_pval}
                logger.debug("    - %s: %s 后仍不平稳 (p=%.3f), 使用 %s", col, transform_type.capitalize(), diff_pval, transform_type.capitalize())

    logger.info("[Stationarity Check] 检查和转换完成. 输出 Shape: %s", transformed_data.shape)
    total_removed = sum(len(v) for v in removed_cols_info.values())
    if total_removed > 0:
        logger.info("  [!] 共移除了 %d 个变量:", total_removed)
        for reason, cols in removed_cols_info.items():
            if cols:
                logger.info("      - 因 '%s' 移除 (%d 个): %s%s", reason, len(cols), ', '.join(cols[:5]), '...' if len(cols)>5 else '')

    return transformed_data, transform_log, removed_cols_info

def apply_stationarity_transforms(
    data: pd.DataFrame,
    transform_rules: Dict[str, Dict[str, Any]]
) -> pd.DataFrame:
    """
    根据提供的规则字典对DataFrame中的变量应用平稳性转换

    如果某个变量在规则字典中找不到，则保留其原始值

    Args:
        data: 包含原始（或预处理）数据的DataFrame
        transform_rules: 转换规则字典，键是变量名，值是包含转换状态的字典
                        例如 {'status': 'level'}, {'status': 'diff'}, {'status': 'log_diff'}

    Returns:
        pd.DataFrame: 应用转换后的DataFrame
    """
    logger.info("[Apply Stationarity V2] 开始根据提供的规则应用平稳性转换")
    transformed_data = pd.DataFrame(index=data.index)
    applied_count = 0
    level_kept_count = 0

    # 遍历输入数据的每一列
    for col in data.columns:
        rule_info = transform_rules.get(col, None)
        status = 'level'  # 默认保留Level

        if rule_info and isinstance(rule_info, dict) and 'status' in rule_info:
            # 如果找到有效规则，则使用规则中的status
            status = rule_info['status'].lower()

        try:
            series = data[col]
            if status == 'diff':
                transformed_data[col] = series.diff(1)
                applied_count += 1
            elif status == 'log_diff':
                # 检查是否有非正值
                series_clean = series.dropna()
                if len(series_clean) == 0:
                    raise ValueError(f"变量 '{col}' 全为NaN，无法应用 'log_diff'")
                if (series_clean <= 0).any():
                    raise ValueError(f"变量 '{col}' 包含非正值，无法应用 'log_diff'")
                transformed_data[col] = np.log(series).diff(1)
                applied_count += 1
            else:  # status == 'level' 或其他未知/跳过状态
                transformed_data[col] = series.copy()
                level_kept_count += 1

        except Exception as e:
            logger.error("    错误: 应用规则 '%s' 到变量 '%s' 时出错: %s", status, col, e)
            raise RuntimeError(f"应用规则 '{status}' 到变量 '{col}' 失败") from e

    logger.info("[Apply Stationarity V2] 转换应用完成")
    logger.info("    成功应用 'diff'/'log_diff': %d 个变量", applied_count)
    logger.info("    保留 Level (无规则或规则指示): %d 个变量", level_kept_count)
    logger.info("    输入 Shape: %s, 输出 Shape: %s", data.shape, transformed_data.shape)

    # 移除转换后全为NaN的列
    all_nan_cols = transformed_data.columns[transformed_data.isnull().all()].tolist()
    if all_nan_cols:
        logger.warning("    警告：以下列在转换后全为 NaN，将被移除: %s", all_nan_cols)
        transformed_data = transformed_data.drop(columns=all_nan_cols)
        logger.info("    移除全 NaN 列后 Shape: %s", transformed_data.shape)

    # 确保输出包含所有原始列（即使转换失败也保留原列）
    if set(transformed_data.columns) != set(data.columns):
         logger.warning("    警告：输出列与输入列不完全匹配！正在尝试重新对齐...")
         transformed_data = transformed_data.reindex(columns=data.columns, fill_value=np.nan)

    return transformed_data

# 导出的函数
__all__ = [
    'ensure_stationarity',
    'apply_stationarity_transforms'
]
