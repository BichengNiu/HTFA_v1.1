# -*- coding: utf-8 -*-
"""
矩阵和数据验证工具模块

提供统一的验证函数，消除代码重复
"""

import numpy as np
from typing import Dict, Optional
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


def validate_sample_size(
    n_samples: int,
    n_params: int,
    min_extra: int = 2,
    context: Optional[str] = None
) -> None:
    """
    验证样本数量是否足够进行估计

    Args:
        n_samples: 样本数量
        n_params: 参数数量
        min_extra: 最小额外样本数（用于自由度）
        context: 上下文信息（用于错误信息）

    Raises:
        ValueError: 如果样本数量不足
    """
    min_required = n_params + min_extra
    if n_samples < min_required:
        ctx = f" ({context})" if context else ""
        raise ValueError(
            f"样本数量不足{ctx}: 当前{n_samples}个样本，"
            f"至少需要{min_required}个样本（参数数{n_params} + {min_extra}）"
        )


def validate_positive_definite(
    mat: np.ndarray,
    name: str,
    tolerance: float = 1e-10
) -> None:
    """
    验证矩阵是否正定

    Args:
        mat: 待验证的矩阵
        name: 矩阵名称
        tolerance: 最小特征值容差

    Raises:
        ValueError: 如果矩阵不是正定的
    """
    if mat.shape[0] != mat.shape[1]:
        raise ValueError(f"矩阵'{name}'不是方阵: {mat.shape}")

    try:
        eigenvalues = np.linalg.eigvalsh(mat)
        min_eigenvalue = np.min(eigenvalues)
        if min_eigenvalue < tolerance:
            raise ValueError(
                f"矩阵'{name}'不是正定的: 最小特征值={min_eigenvalue:.2e}"
            )
    except np.linalg.LinAlgError as e:
        raise ValueError(f"矩阵'{name}'特征值计算失败: {e}")


def validate_dimensions(
    mat: np.ndarray,
    expected_shape: tuple,
    name: str
) -> None:
    """
    验证矩阵维度

    Args:
        mat: 待验证的矩阵
        expected_shape: 期望的形状（可以用-1表示任意维度）
        name: 矩阵名称

    Raises:
        ValueError: 如果维度不匹配
    """
    if len(mat.shape) != len(expected_shape):
        raise ValueError(
            f"矩阵'{name}'维度数不匹配: 期望{len(expected_shape)}维，"
            f"实际{len(mat.shape)}维"
        )

    for i, (actual, expected) in enumerate(zip(mat.shape, expected_shape)):
        if expected != -1 and actual != expected:
            raise ValueError(
                f"矩阵'{name}'第{i}维大小不匹配: 期望{expected}，实际{actual}"
            )


__all__ = [
    'validate_matrix',
    'validate_matrices',
    'validate_sample_size',
    'validate_positive_definite',
    'validate_dimensions'
]
