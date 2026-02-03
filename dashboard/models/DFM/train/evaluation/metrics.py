# -*- coding: utf-8 -*-
"""
指标计算模块

计算模型评估指标，支持平均RMSE和混频RMSE
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
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


def calculate_mixed_frequency_rmse(
    observation_data: np.ndarray,
    reconstructed_data: np.ndarray,
    time_index: pd.DatetimeIndex,
    variable_names: List[str],
    var_frequency_map: Dict[str, str],
    rmse_alignment: str = 'current'
) -> Tuple[float, Dict[str, float]]:
    """
    计算混频数据的RMSE

    对于月度变量：将当月所有周的重构值取平均，与该月实际值对比
    对于周度变量：直接逐周对比

    对齐方式：
    - 当月对齐 (current): 月份N所有周的重构值平均 vs 月份N的唯一真实值
    - 下月对齐 (next): 月份N所有周的重构值平均 vs 月份N+1的唯一真实值

    Args:
        observation_data: 观测数据 (n_time, n_vars)
        reconstructed_data: 重构数据 (n_time, n_vars)
        time_index: 时间索引 (DatetimeIndex)
        variable_names: 变量名列表
        var_frequency_map: 变量频率映射 {变量名: 频率}
        rmse_alignment: RMSE计算对齐方式 ('current'=当月对齐, 'next'=下月对齐)

    Returns:
        Tuple[float, Dict[str, float]]: (平均RMSE, 各变量RMSE字典)
    """
    n_vars = observation_data.shape[1]
    rmse_dict = {}

    for i in range(n_vars):
        var_name = variable_names[i] if i < len(variable_names) else f"var_{i}"
        freq = var_frequency_map.get(var_name, '周').lower()

        # 判断是否为月度变量
        is_monthly = '月' in freq or 'monthly' in freq or freq == 'm'

        if is_monthly:
            # 月度变量：按月聚合重构值，支持对齐方式
            rmse = _calculate_monthly_aggregated_rmse(
                observation_data[:, i],
                reconstructed_data[:, i],
                time_index,
                alignment=rmse_alignment
            )
        else:
            # 周度变量：根据对齐方式计算
            if rmse_alignment == 'next' and len(observation_data) > 1:
                # 下月对齐：预测值[t] vs 实际值[t+1]
                obs_aligned = observation_data[1:, i]
                recon_aligned = reconstructed_data[:-1, i]
                residuals = obs_aligned - recon_aligned
            else:
                # 当月对齐（默认）
                residuals = observation_data[:, i] - reconstructed_data[:, i]
            rmse = np.sqrt(np.nanmean(residuals ** 2))

        rmse_dict[var_name] = rmse

    # 计算平均RMSE
    valid_rmses = [r for r in rmse_dict.values() if np.isfinite(r)]
    avg_rmse = float(np.mean(valid_rmses)) if valid_rmses else np.inf

    return avg_rmse, rmse_dict


def _calculate_monthly_aggregated_rmse(
    obs_series: np.ndarray,
    recon_series: np.ndarray,
    time_index: pd.DatetimeIndex,
    alignment: str = 'current'
) -> float:
    """
    计算月度变量的聚合RMSE

    将每月的重构值取平均，与该月（或下月）实际值对比

    Args:
        obs_series: 观测序列
        recon_series: 重构序列
        time_index: 时间索引
        alignment: 对齐方式 ('current'=当月对齐, 'next'=下月对齐)

    Returns:
        float: RMSE值
    """
    # 创建DataFrame便于按月分组
    df = pd.DataFrame({
        'obs': obs_series,
        'recon': recon_series,
        'year_month': time_index.to_period('M')
    })

    # 按月聚合重构值（所有周的平均）
    monthly_recon = df.groupby('year_month')['recon'].mean()

    # 按月获取真实值（每月只有一个非NaN值，取该值）
    monthly_obs = df.groupby('year_month')['obs'].apply(
        lambda x: x.dropna().iloc[0] if len(x.dropna()) > 0 else np.nan
    )

    residuals = []
    months = monthly_recon.index.tolist()

    if alignment == 'next':
        # 下月对齐：本月重构平均 vs 下月真实值
        for i in range(len(months) - 1):
            recon_val = monthly_recon.iloc[i]
            obs_val = monthly_obs.iloc[i + 1]  # 下个月的真实值
            if pd.notna(recon_val) and pd.notna(obs_val):
                residuals.append(obs_val - recon_val)
    else:
        # 当月对齐：本月重构平均 vs 本月真实值
        for i in range(len(months)):
            recon_val = monthly_recon.iloc[i]
            obs_val = monthly_obs.iloc[i]
            if pd.notna(recon_val) and pd.notna(obs_val):
                residuals.append(obs_val - recon_val)

    if not residuals:
        return np.inf

    return float(np.sqrt(np.mean(np.array(residuals) ** 2)))


__all__ = [
    'calculate_average_reconstruction_rmse',
    'calculate_single_variable_rmse',
    'compare_model_scores',
    'calculate_mixed_frequency_rmse',
]
