# -*- coding: utf-8 -*-
"""
因子预测模块

基于AR模型预测未来因子值（经典DFM，无目标变量）
"""

import numpy as np
import pandas as pd
from typing import Optional
from dashboard.models.DFM.train.core.models import DFMModelResult
from dashboard.models.DFM.train.utils.logger import get_logger

logger = get_logger(__name__)


def generate_factor_forecast(
    model_result: DFMModelResult,
    n_periods: int = 1
) -> np.ndarray:
    """
    基于AR模型预测未来因子值

    使用状态转移矩阵A预测未来n_periods期的因子值。

    Args:
        model_result: DFM模型结果，包含状态转移矩阵A和平滑因子
        n_periods: 预测期数

    Returns:
        预测的因子值 (n_periods, n_factors)

    Raises:
        ValueError: 如果模型结果缺少必要参数
    """
    if model_result.A is None:
        raise ValueError("模型结果缺少状态转移矩阵A")
    if model_result.factors_smooth is None:
        raise ValueError("模型结果缺少平滑因子")

    A = model_result.A
    factors = model_result.factors_smooth  # (n_factors, n_time)

    # 获取最后一个时刻的因子状态
    last_state = factors[:, -1]

    # 使用状态转移矩阵预测
    forecasts = []
    current_state = last_state.copy()

    for _ in range(n_periods):
        next_state = A @ current_state
        forecasts.append(next_state.copy())
        current_state = next_state

    result = np.array(forecasts)  # (n_periods, n_factors)

    logger.debug(f"因子预测完成: {n_periods}期, 因子数={factors.shape[0]}")

    return result


def reconstruct_observations(
    model_result: DFMModelResult,
    factor_values: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    基于因子重构观测变量

    使用载荷矩阵H将因子映射回观测空间。

    Args:
        model_result: DFM模型结果，包含载荷矩阵H
        factor_values: 因子值 (n_time, n_factors)，如果为None则使用平滑因子

    Returns:
        重构的观测值 (n_time, n_obs)

    Raises:
        ValueError: 如果模型结果缺少必要参数
    """
    if model_result.H is None:
        raise ValueError("模型结果缺少载荷矩阵H")

    H_full = model_result.H
    # 从 factors_smooth 获取因子数（DDFM 模型的 H 包含特质项）
    n_factors = model_result.factors_smooth.shape[0] if model_result.factors_smooth is not None else H_full.shape[1]
    H = H_full[:, :n_factors]  # (n_obs, n_factors)

    if factor_values is None:
        if model_result.factors_smooth is None:
            raise ValueError("模型结果缺少平滑因子")
        factor_values = model_result.factors_smooth.T  # (n_time, n_factors)

    # 重构观测值: y = F @ H.T
    reconstructed = factor_values @ H.T  # (n_time, n_obs)

    logger.debug(f"观测重构完成: shape={reconstructed.shape}")

    return reconstructed


def forecast_observations(
    model_result: DFMModelResult,
    n_periods: int = 1
) -> np.ndarray:
    """
    预测未来观测变量值

    先预测因子，再通过载荷矩阵映射到观测空间。

    Args:
        model_result: DFM模型结果
        n_periods: 预测期数

    Returns:
        预测的观测值 (n_periods, n_obs)
    """
    # 预测因子
    factor_forecast = generate_factor_forecast(model_result, n_periods)

    # 重构观测
    obs_forecast = reconstruct_observations(model_result, factor_forecast)

    logger.debug(f"观测预测完成: {n_periods}期, 变量数={obs_forecast.shape[1]}")

    return obs_forecast


__all__ = [
    'generate_factor_forecast',
    'reconstruct_observations',
    'forecast_observations'
]
