# -*- coding: utf-8 -*-
"""
数据验证工具模块

提供统一的数据验证功能，消除各个模块中的重复验证逻辑
"""

import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np

from dashboard.explore.core.constants import (
    MIN_SAMPLES_ADF,
    MIN_SAMPLES_CORRELATION,
    MIN_SAMPLES_KL_DIVERGENCE,
    MIN_SAMPLES_WIN_RATE,
    ERROR_MESSAGES
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果数据类"""
    is_valid: bool
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    cleaned_data: Optional[pd.Series] = None
    metadata: Optional[dict] = None


def validate_series(
    series: pd.Series,
    min_samples: int = MIN_SAMPLES_CORRELATION,
    require_numeric: bool = True,
    series_name: Optional[str] = None
) -> ValidationResult:
    """
    验证单个序列的有效性

    Args:
        series: 待验证的序列
        min_samples: 最小样本数要求
        require_numeric: 是否要求数值类型
        series_name: 序列名称（用于错误消息）

    Returns:
        ValidationResult: 验证结果
    """
    name = series_name or series.name or "未命名序列"

    # 检查序列是否为空
    if series is None or series.empty:
        logger.warning(f"序列 '{name}' 为空")
        return ValidationResult(
            is_valid=False,
            error_message=f"序列 '{name}' {ERROR_MESSAGES['empty_series']}"
        )

    # 数值类型检查和转换
    if require_numeric:
        if not pd.api.types.is_numeric_dtype(series):
            # 尝试转换为数值类型
            try:
                series_numeric = pd.to_numeric(series, errors='coerce')
            except Exception as e:
                logger.error(f"序列 '{name}' 无法转换为数值类型: {e}")
                return ValidationResult(
                    is_valid=False,
                    error_message=f"序列 '{name}' {ERROR_MESSAGES['not_numeric']}"
                )
        else:
            series_numeric = series
    else:
        series_numeric = series

    # 清理NaN值
    series_clean = series_numeric.dropna()

    # 检查有效样本数
    n_valid = len(series_clean)
    if n_valid < min_samples:
        logger.warning(f"序列 '{name}' 有效样本数不足: {n_valid} < {min_samples}")
        return ValidationResult(
            is_valid=False,
            error_message=f"序列 '{name}' {ERROR_MESSAGES['insufficient_data']} (需要 >= {min_samples}, 实际 {n_valid})",
            cleaned_data=series_clean,
            metadata={'n_valid': n_valid, 'n_total': len(series)}
        )

    # 检查方差（对于需要计算标准差的场景）
    if require_numeric and n_valid > 1:
        variance = series_clean.var()
        if variance == 0 or np.isnan(variance):
            logger.warning(f"序列 '{name}' 方差为零")
            return ValidationResult(
                is_valid=False,
                error_message=f"序列 '{name}' {ERROR_MESSAGES['no_variance']}",
                cleaned_data=series_clean,
                metadata={'n_valid': n_valid, 'variance': variance}
            )

    # 验证通过
    logger.debug(f"序列 '{name}' 验证通过: {n_valid} 个有效样本")
    return ValidationResult(
        is_valid=True,
        cleaned_data=series_clean,
        metadata={'n_valid': n_valid, 'n_total': len(series)}
    )


def validate_series_pair(
    series1: pd.Series,
    series2: pd.Series,
    min_samples: int = MIN_SAMPLES_CORRELATION,
    series1_name: Optional[str] = None,
    series2_name: Optional[str] = None
) -> ValidationResult:
    """
    验证序列对的有效性

    Args:
        series1: 第一个序列
        series2: 第二个序列
        min_samples: 最小样本数要求
        series1_name: 第一个序列名称
        series2_name: 第二个序列名称

    Returns:
        ValidationResult: 验证结果，cleaned_data包含对齐后的两个序列
    """
    name1 = series1_name or series1.name or "序列1"
    name2 = series2_name or series2.name or "序列2"

    # 分别验证两个序列
    result1 = validate_series(series1, min_samples=1, series_name=name1)
    if not result1.is_valid:
        return ValidationResult(
            is_valid=False,
            error_message=result1.error_message
        )

    result2 = validate_series(series2, min_samples=1, series_name=name2)
    if not result2.is_valid:
        return ValidationResult(
            is_valid=False,
            error_message=result2.error_message
        )

    # 对齐两个序列的索引
    combined = pd.DataFrame({
        'series1': result1.cleaned_data,
        'series2': result2.cleaned_data
    }).dropna()

    # 检查对齐后的样本数
    n_common = len(combined)
    if n_common < min_samples:
        logger.warning(f"序列对 '{name1}' 和 '{name2}' 对齐后样本数不足: {n_common} < {min_samples}")
        return ValidationResult(
            is_valid=False,
            error_message=f"序列对对齐后{ERROR_MESSAGES['insufficient_data']} (需要 >= {min_samples}, 实际 {n_common})",
            metadata={
                'n_common': n_common,
                'n_series1': len(result1.cleaned_data),
                'n_series2': len(result2.cleaned_data)
            }
        )

    # 验证通过
    logger.debug(f"序列对 '{name1}' 和 '{name2}' 验证通过: {n_common} 个共同样本")
    return ValidationResult(
        is_valid=True,
        cleaned_data=(combined['series1'], combined['series2']),
        metadata={
            'n_common': n_common,
            'n_series1_original': len(series1),
            'n_series2_original': len(series2)
        }
    )


def validate_analysis_inputs(
    df: pd.DataFrame,
    target_var: str,
    candidate_vars: List[str],
    min_samples: int = MIN_SAMPLES_CORRELATION
) -> Tuple[List[str], List[str]]:
    """
    验证分析输入（批量分析的标准验证）

    Args:
        df: 输入DataFrame
        target_var: 目标变量名
        candidate_vars: 候选变量名列表
        min_samples: 最小样本数

    Returns:
        Tuple[错误消息列表, 警告消息列表]
    """
    errors = []
    warnings = []

    # 验证输入不为空
    if not target_var:
        errors.append("目标变量未选择")

    if not candidate_vars:
        warnings.append("候选变量列表为空")
        return errors, warnings

    # 验证DataFrame
    if df is None or df.empty:
        errors.append("输入数据为空")
        return errors, warnings

    # 验证目标变量
    if target_var and target_var not in df.columns:
        errors.append(f"目标变量 '{target_var}' 不存在于数据中")
    elif target_var:
        result = validate_series(df[target_var], min_samples, series_name=target_var)
        if not result.is_valid:
            errors.append(result.error_message)

    # 验证候选变量
    for var in candidate_vars:
        if var not in df.columns:
            warnings.append(f"候选变量 '{var}' 不存在于数据中")

    return errors, warnings
