"""
数据验证工具模块

提供统一的数据验证功能，消除各个模块中的重复验证逻辑
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from htfa.exploration.core.constants import ERROR_MESSAGES, MIN_SAMPLES_CORRELATION

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果数据类"""
    is_valid: bool
    error_message: str | None = None
    cleaned_data: pd.Series | None = None
    metadata: dict | None = None


def validate_real_series(
    series: pd.Series,
    *,
    dropna: bool = False,
) -> pd.Series:
    """校验并返回实数型浮点 Series 副本。

    统一的"实数数值序列"校验入口，供平稳性检验与结构突变检验共用。

    Args:
        series: 待校验的序列
        dropna: 是否在返回前丢弃 NaN

    Returns:
        浮点副本（dropna=True 时不含 NaN）

    Raises:
        TypeError: 非 Series、或非实数数值型（含 bool/complex）
        ValueError: 空序列、包含无穷值
    """
    if not isinstance(series, pd.Series):
        raise TypeError("分析对象必须是 pandas.Series")
    if series.empty:
        raise ValueError("序列不能为空")
    if (
        not pd.api.types.is_numeric_dtype(series.dtype)
        or pd.api.types.is_bool_dtype(series.dtype)
        or pd.api.types.is_complex_dtype(series.dtype)
    ):
        raise TypeError("序列必须是实数型变量")

    converted = series.astype(float)
    if dropna:
        converted = converted.dropna()
        if converted.empty:
            raise ValueError("序列不能为空")

    values = converted.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise ValueError("序列包含无穷值")
    return converted


def validate_series(
    series: pd.Series,
    min_samples: int = MIN_SAMPLES_CORRELATION,
    require_numeric: bool = True,
    series_name: str | None = None
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
            except (TypeError, ValueError) as e:
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


def validate_analysis_inputs(
    df: pd.DataFrame,
    target_var: str,
    candidate_vars: list[str],
    min_samples: int = MIN_SAMPLES_CORRELATION
) -> tuple[list[str], list[str]]:
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
    warnings.extend(
        f"候选变量 '{var}' 不存在于数据中"
        for var in candidate_vars
        if var not in df.columns
    )

    return errors, warnings
