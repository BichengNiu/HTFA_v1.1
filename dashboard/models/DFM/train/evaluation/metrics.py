# -*- coding: utf-8 -*-
"""
指标计算模块

计算模型评估指标，支持目标变量RMSE和加权RMSE
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.core.models import DFMModelResult, EvaluationMetrics


logger = get_logger(__name__)


def calculate_target_reconstruction_rmse(
    observation_data: np.ndarray,
    reconstructed_data: np.ndarray,
    target_idx: int
) -> float:
    """
    计算目标变量重构RMSE

    Args:
        observation_data: 观测数据 (n_time, n_obs)
        reconstructed_data: 重构数据 (n_time, n_obs)
        target_idx: 目标变量在列中的索引

    Returns:
        float: 目标变量重构RMSE
    """
    target_obs = observation_data[:, target_idx]
    target_recon = reconstructed_data[:, target_idx]
    residuals = target_obs - target_recon
    return float(np.sqrt(np.nanmean(residuals ** 2)))


def calculate_weighted_rmse(
    train_rmse: float,
    val_rmse: float,
    training_weight: float
) -> float:
    """
    计算加权RMSE

    Args:
        train_rmse: 训练期RMSE
        val_rmse: 验证期RMSE
        training_weight: 训练期权重 (0.0-1.0)

    Returns:
        float: 加权RMSE
    """
    # 处理无效值
    if not np.isfinite(train_rmse) and not np.isfinite(val_rmse):
        return np.inf
    if not np.isfinite(train_rmse):
        return val_rmse
    if not np.isfinite(val_rmse):
        return train_rmse

    return training_weight * train_rmse + (1.0 - training_weight) * val_rmse


def evaluate_dfm_model(
    model_result: DFMModelResult,
    observation_data: pd.DataFrame,
    training_start: str,
    train_end: str,
    target_variable: Optional[str] = None,
    validation_start: Optional[str] = None,
    validation_end: Optional[str] = None,
    training_weight: float = 0.5
) -> EvaluationMetrics:
    """
    评估DFM模型拟合质量

    基于目标变量重构RMSE的评估，支持训练期和验证期加权。

    Args:
        model_result: DFM模型结果
        observation_data: 观测数据
        training_start: 训练期开始日期
        train_end: 训练期结束日期
        target_variable: 目标变量名称（可选，不指定则使用第一个变量）
        validation_start: 验证期开始日期（可选）
        validation_end: 验证期结束日期（可选）
        training_weight: 训练期权重 (0.0-1.0)

    Returns:
        EvaluationMetrics: 包含目标变量RMSE的评估指标对象
    """
    # 确定目标变量索引
    if target_variable and target_variable in observation_data.columns:
        target_idx = observation_data.columns.get_loc(target_variable)
    else:
        target_idx = 0  # 默认使用第一个变量
        if target_variable:
            logger.warning(f"目标变量'{target_variable}'不在数据中，使用第一个变量")

    # 获取训练期数据
    train_start_dt = pd.to_datetime(training_start)
    train_end_dt = pd.to_datetime(train_end)
    train_data = observation_data[
        (observation_data.index >= train_start_dt) &
        (observation_data.index <= train_end_dt)
    ]

    n_time = len(train_data)

    # 计算目标变量训练期RMSE
    target_rmse = np.inf

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

            # 计算目标变量训练期RMSE
            target_rmse = calculate_target_reconstruction_rmse(
                obs_centered, reconstructed, target_idx
            )

            # 存储重构数据
            model_result.reconstructed_data = reconstructed

        except Exception as e:
            logger.warning(f"训练期目标变量RMSE计算失败: {e}")

    # 计算验证期目标变量RMSE
    target_rmse_validation = np.inf
    if validation_start and validation_end:
        try:
            val_start_dt = pd.to_datetime(validation_start)
            val_end_dt = pd.to_datetime(validation_end)
            val_data = observation_data[
                (observation_data.index >= val_start_dt) &
                (observation_data.index <= val_end_dt)
            ]

            if len(val_data) > 0 and model_result.H is not None and model_result.factors_smooth is not None:
                H = model_result.H
                factors = model_result.factors_smooth.T  # (n_time, n_factors)

                # 计算验证期对应的因子索引范围
                full_data = observation_data[
                    (observation_data.index >= train_start_dt) &
                    (observation_data.index <= val_end_dt)
                ]
                val_start_idx = len(full_data) - len(val_data)
                val_end_idx = len(full_data)

                # 确保因子数据足够
                if factors.shape[0] >= val_end_idx:
                    val_factors = factors[val_start_idx:val_end_idx, :]
                    val_reconstructed = val_factors @ H.T

                    # 中心化验证期数据（使用训练期均值）
                    train_mean = np.nanmean(train_data.values, axis=0)
                    val_obs_centered = val_data.values - train_mean

                    # 确保维度匹配
                    min_val_time = min(val_obs_centered.shape[0], val_reconstructed.shape[0])
                    val_obs_centered = val_obs_centered[:min_val_time, :]
                    val_reconstructed = val_reconstructed[:min_val_time, :]

                    # 计算目标变量验证期RMSE
                    target_rmse_validation = calculate_target_reconstruction_rmse(
                        val_obs_centered, val_reconstructed, target_idx
                    )

        except Exception as e:
            logger.warning(f"验证期目标变量RMSE计算失败: {e}")

    # 计算加权RMSE
    weighted_target_rmse = calculate_weighted_rmse(
        target_rmse, target_rmse_validation, training_weight
    )

    return EvaluationMetrics(
        target_rmse=target_rmse,
        target_rmse_validation=target_rmse_validation,
        weighted_target_rmse=weighted_target_rmse,
        converged=model_result.converged,
        iterations=model_result.iterations
    )


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
    'calculate_target_reconstruction_rmse',
    'calculate_weighted_rmse',
    'evaluate_dfm_model',
    'compare_model_scores'
]
