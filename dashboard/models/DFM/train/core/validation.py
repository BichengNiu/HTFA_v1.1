# -*- coding: utf-8 -*-
"""
矩阵和数据验证工具模块

提供统一的验证函数，消除代码重复
"""

import numpy as np
from typing import Dict
from dashboard.models.DFM.train.utils.logger import get_logger

logger = get_logger(__name__)


def validate_matrix(
    mat: np.ndarray,
    name: str,
    allow_nan: bool = False,
    allow_inf: bool = False
) -> None:
    """
    验证矩阵数值有效性

    Args:
        mat: 待验证的矩阵
        name: 矩阵名称（用于错误信息）
        allow_nan: 是否允许NaN值
        allow_inf: 是否允许Inf值

    Raises:
        ValueError: 如果矩阵包含无效值
    """
    if mat is None:
        raise ValueError(f"矩阵'{name}'为None")

    if not isinstance(mat, np.ndarray):
        raise TypeError(f"矩阵'{name}'必须是numpy数组，当前类型: {type(mat)}")

    nan_count = np.sum(np.isnan(mat))
    inf_count = np.sum(np.isinf(mat))

    errors = []
    if not allow_nan and nan_count > 0:
        errors.append(f"包含{nan_count}个NaN值")
    if not allow_inf and inf_count > 0:
        errors.append(f"包含{inf_count}个Inf值")

    if errors:
        raise ValueError(f"矩阵'{name}'无效: {', '.join(errors)}")


def validate_matrices(
    matrices: Dict[str, np.ndarray],
    allow_nan: bool = False,
    allow_inf: bool = False
) -> None:
    """
    批量验证多个矩阵

    Args:
        matrices: 矩阵字典 {名称: 矩阵}
        allow_nan: 是否允许NaN值
        allow_inf: 是否允许Inf值

    Raises:
        ValueError: 如果任何矩阵包含无效值
    """
    for name, mat in matrices.items():
        validate_matrix(mat, name, allow_nan, allow_inf)


__all__ = [
    'validate_matrix',
    'validate_matrices',
]
