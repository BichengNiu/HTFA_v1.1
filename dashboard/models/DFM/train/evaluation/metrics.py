# -*- coding: utf-8 -*-
"""
指标计算模块

计算模型评估指标，支持平均RMSE
"""

import numpy as np
from dashboard.models.DFM.train.utils.logger import get_logger


logger = get_logger(__name__)


def calculate_average_reconstruction_rmse(
    observation_data: np.ndarray,
    reconstructed_data: np.ndarray
) -> float:
    """
    计算所有变量的平均重构RMSE

    Args:
        observation_data: 观测数据 (n_time, n_obs)
        reconstructed_data: 重构数据 (n_time, n_obs)

    Returns:
        float: 所有变量的平均RMSE
    """
    n_vars = observation_data.shape[1]
    rmse_list = []
    for i in range(n_vars):
        residuals = observation_data[:, i] - reconstructed_data[:, i]
        rmse = np.sqrt(np.nanmean(residuals ** 2))
        rmse_list.append(rmse)
    return float(np.mean(rmse_list))


def calculate_single_variable_rmse(
    observation_data: np.ndarray,
    reconstructed_data: np.ndarray,
    variable_index: int
) -> float:
    """
    计算单个变量的重构RMSE

    Args:
        observation_data: 观测数据 (n_time, n_obs)
        reconstructed_data: 重构数据 (n_time, n_obs)
        variable_index: 目标变量的索引

    Returns:
        float: 单个变量的RMSE
    """
    if variable_index < 0 or variable_index >= observation_data.shape[1]:
        logger.warning(f"变量索引 {variable_index} 超出范围，返回inf")
        return np.inf

    residuals = observation_data[:, variable_index] - reconstructed_data[:, variable_index]
    rmse = np.sqrt(np.nanmean(residuals ** 2))
    return float(rmse)


def compare_model_scores(score_a: float, score_b: float) -> int:
    """
    比较两个模型得分（RMSE，越小越好）

    Args:
        score_a: 模型A的RMSE
        score_b: 模型B的RMSE

    Returns:
        int: 1 if A更好（更小）, -1 if B更好, 0 if 相等
    """
    # 处理无效值
    if not np.isfinite(score_a) and not np.isfinite(score_b):
        return 0
    if not np.isfinite(score_a):
        return -1
    if not np.isfinite(score_b):
        return 1

    # RMSE越小越好
    if score_a < score_b:
        return 1
    elif score_a > score_b:
        return -1

    return 0


__all__ = [
    'calculate_average_reconstruction_rmse',
    'calculate_single_variable_rmse',
    'compare_model_scores'
]
