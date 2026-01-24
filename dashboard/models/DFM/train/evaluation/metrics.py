# -*- coding: utf-8 -*-
"""
指标计算模块

计算模型评估指标（经典DFM版，只保留重构RMSE）
"""

import pandas as pd
import numpy as np
from typing import Tuple
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.core.models import DFMModelResult, EvaluationMetrics


logger = get_logger(__name__)


def calculate_reconstruction_rmse(
    observation_data: np.ndarray,
    reconstructed_data: np.ndarray
) -> float:
    """
    计算重构RMSE

    Args:
        observation_data: 观测数据 (n_time, n_obs)
        reconstructed_data: 重构数据 (n_time, n_obs)

    Returns:
        float: 重构RMSE
    """
    residuals = observation_data - reconstructed_data
    rmse = np.sqrt(np.nanmean(residuals ** 2))
    return float(rmse)


def evaluate_dfm_model(
    model_result: DFMModelResult,
    observation_data: pd.DataFrame,
    training_start: str,
    train_end: str
) -> EvaluationMetrics:
    """
    评估DFM模型拟合质量

    基于模型拟合质量的评估，只计算重构RMSE。

    Args:
        model_result: DFM模型结果
        observation_data: 观测数据
        training_start: 训练期开始日期
        train_end: 训练期结束日期

    Returns:
        EvaluationMetrics: 包含重构RMSE的评估指标对象
    """
    # 获取训练期数据
    train_start_dt = pd.to_datetime(training_start)
    train_end_dt = pd.to_datetime(train_end)
    train_data = observation_data[
        (observation_data.index >= train_start_dt) &
        (observation_data.index <= train_end_dt)
    ]

    n_time = len(train_data)

    # 计算重构RMSE
    reconstruction_rmse = np.inf

    if model_result.H is not None and model_result.factors_smooth is not None:
        try:
            H = model_result.H
            factors = model_result.factors_smooth.T  # (n_time, n_factors)

            # 确保维度匹配
            if factors.shape[0] >= n_time:
                factors = factors[:n_time, :]

            reconstructed = factors @ H.T

            # 中心化观测数据
            obs_values = train_data.values
            obs_mean = np.nanmean(obs_values, axis=0)
            obs_centered = obs_values - obs_mean

            # 确保维度匹配
            min_time = min(obs_centered.shape[0], reconstructed.shape[0])
            obs_centered = obs_centered[:min_time, :]
            reconstructed = reconstructed[:min_time, :]

            # 计算重构RMSE
            reconstruction_rmse = calculate_reconstruction_rmse(obs_centered, reconstructed)

            # 存储重构数据
            model_result.reconstructed_data = reconstructed

        except Exception as e:
            logger.warning(f"重构误差计算失败: {e}")

    return EvaluationMetrics(
        reconstruction_rmse=reconstruction_rmse,
        converged=model_result.converged,
        iterations=model_result.iterations
    )


def compare_model_scores(score_a: float, score_b: float) -> int:
    """
    比较两个模型得分（重构RMSE，越小越好）

    Args:
        score_a: 模型A的重构RMSE
        score_b: 模型B的重构RMSE

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

    # 重构RMSE越小越好
    if score_a < score_b:
        return 1
    elif score_a > score_b:
        return -1

    return 0


__all__ = [
    'calculate_reconstruction_rmse',
    'evaluate_dfm_model',
    'compare_model_scores'
]
