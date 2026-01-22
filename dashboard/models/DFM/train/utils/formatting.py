# -*- coding: utf-8 -*-
"""
格式化工具模块

提供训练结果的格式化和打印功能
"""

import numpy as np
import pandas as pd
from typing import Optional, Callable
from dashboard.models.DFM.train.core.models import TrainingResult


def format_training_config(
    train_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
    train_samples: int,
    validation_samples: int,
    initial_vars: int,
    k_factors: int,
    is_ddfm: bool = False
) -> str:
    """
    格式化训练配置摘要

    Args:
        train_start: 训练期开始日期
        train_end: 训练期结束日期
        validation_start: 验证期/观察期开始日期
        validation_end: 验证期/观察期结束日期
        train_samples: 训练样本数
        validation_samples: 验证期/观察期样本数
        initial_vars: 初始变量数
        k_factors: 因子数
        is_ddfm: 是否为DDFM模式

    Returns:
        str: 格式化的配置摘要字符串
    """
    period_label = "观察期" if is_ddfm else "验证期"
    config_summary = f"""
========== 训练配置 ==========
训练期: {train_start} ~ {train_end} (样本数: {train_samples})
{period_label}: {validation_start} ~ {validation_end} (样本数: {validation_samples})
初始变量数: {initial_vars}
因子数: {k_factors}
============================
"""
    return config_summary


def format_training_summary(result: TrainingResult) -> str:
    """
    格式化训练摘要（精简版）

    将TrainingResult对象格式化为精简的摘要。

    Args:
        result: 训练结果对象

    Returns:
        str: 格式化的摘要字符串
    """
    lines = [
        "========== 最终模型 ==========",
        f"最终变量数: {len(result.selected_variables) - 1}",
        f"因子数: {result.k_factors}",
        f"训练期RMSE: {result.metrics.is_rmse:.4f}",
    ]

    # 经典DFM：显示验证期RMSE（用于变量选择）
    if result.metrics.oos_rmse != np.inf:
        lines.append(f"验证期RMSE: {result.metrics.oos_rmse:.4f}")

    # 观察期RMSE（两种模型都显示）
    if result.metrics.obs_rmse != np.inf:
        lines.append(f"观察期RMSE: {result.metrics.obs_rmse:.4f}")

    lines.append(f"训练时间: {result.training_time:.2f}秒")
    lines.append("============================")

    return "\n" + "\n".join(lines) + "\n"


def print_training_summary(
    result: TrainingResult,
    progress_callback: Optional[Callable[[str], None]] = None,
    logger=None
):
    """
    打印训练摘要（精简版）

    将训练摘要输出到日志和进度回调。

    Args:
        result: 训练结果对象
        progress_callback: 进度回调函数 (message: str) -> None
        logger: 日志对象（通常是logging.Logger实例）
    """
    summary = format_training_summary(result)

    # 输出到日志（保留详细信息）
    if logger:
        logger.info(summary)

    # 输出到回调（精简信息，移除[TRAIN]标签）
    if progress_callback:
        progress_callback(summary.strip())


def generate_progress_bar(current: int, total: int, width: int = 20) -> str:
    """
    生成简单的进度条

    Args:
        current: 当前进度值
        total: 总进度值
        width: 进度条宽度（字符数）

    Returns:
        str: 格式化的进度条字符串，如 "[========------------]"
    """
    if total <= 0:
        return "[" + "=" * width + "]"
    percent = min(1.0, current / total)
    filled = int(width * percent)
    bar = '=' * filled + '-' * (width - filled)
    return f"[{bar}]"


def format_win_rate(value: float) -> str:
    """
    格式化胜率显示

    Args:
        value: 胜率值（0-100的百分比）

    Returns:
        str: 格式化的胜率字符串，如 "75.5%" 或 "N/A"
    """
    if np.isfinite(value):
        return f"{value:.1f}%"
    return "N/A"


def format_rmse_change(old_rmse: float, new_rmse: float) -> str:
    """
    格式化RMSE变化

    Args:
        old_rmse: 原RMSE值
        new_rmse: 新RMSE值

    Returns:
        str: 格式化的变化字符串，如 "降低5.2%" 或 "上升3.1%" 或 "N/A"
    """
    if old_rmse <= 0 or not np.isfinite(old_rmse) or not np.isfinite(new_rmse):
        return "N/A"
    pct = (old_rmse - new_rmse) / old_rmse * 100
    if pct >= 0:
        return f"降低{pct:.1f}%"
    return f"上升{abs(pct):.1f}%"


def format_win_rate_change(old_win_rate: float, new_win_rate: float) -> str:
    """
    格式化胜率变化

    Args:
        old_win_rate: 原胜率值
        new_win_rate: 新胜率值

    Returns:
        str: 格式化的变化字符串，如 "提升5.0%" 或 "下降3.0%" 或空字符串
    """
    if not np.isfinite(old_win_rate) or not np.isfinite(new_win_rate):
        return ""
    delta = new_win_rate - old_win_rate
    if delta >= 0:
        return f"提升{delta:.1f}%"
    return f"下降{abs(delta):.1f}%"


__all__ = [
    'format_training_config',
    'format_training_summary',
    'print_training_summary',
    'generate_progress_bar',
    'format_win_rate',
    'format_rmse_change',
    'format_win_rate_change',
]
