# -*- coding: utf-8 -*-
"""
KL散度计算模块

从combined_lead_lag_backend.py中提取并优化的KL散度计算功能
"""

import logging
import math
from typing import Tuple, Optional
import pandas as pd
import numpy as np

from dashboard.explore.core.constants import (
    DEFAULT_KL_SMOOTHING_ALPHA,
    MIN_SAMPLES_KL_DIVERGENCE
)

logger = logging.getLogger(__name__)


def calculate_stata_bins(n: int) -> int:
    """
    使用Stata的自动分箱算法计算分箱数

    公式: bins = min(sqrt(N), 10*log10(N))

    Args:
        n: 样本数量

    Returns:
        分箱数（整数）
    """
    if n <= 0:
        raise ValueError(f"样本数必须大于0，收到: {n}")

    bins_sqrt = math.sqrt(n)
    bins_log = 10 * math.log10(n)
    bins = int(math.ceil(min(bins_sqrt, bins_log)))

    return max(2, bins)


def series_to_distribution(
    series_a: pd.Series,
    series_b: pd.Series,
    bins: Optional[int] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    将两个时间序列转换为离散概率分布

    使用共同的分箱策略来创建可比较的分布

    Args:
        series_a: 第一个序列
        series_b: 第二个序列
        bins: 分箱数（None则使用Stata自动分箱算法）

    Returns:
        Tuple[P分布, Q分布, 分箱边界]

    Raises:
        ValueError: 当序列为空或无法创建分布时
    """
    # 移除NaN值
    series_a_clean = series_a.dropna()
    series_b_clean = series_b.dropna()

    if series_a_clean.empty or series_b_clean.empty:
        raise ValueError("序列在移除NaN后为空，无法创建分布")

    # 自动计算分箱数
    if bins is None:
        n_samples = min(len(series_a_clean), len(series_b_clean))
        bins = calculate_stata_bins(n_samples)

    # 检查常数序列
    series_a_is_constant = len(series_a_clean.unique()) == 1
    series_b_is_constant = len(series_b_clean.unique()) == 1

    if series_a_is_constant and series_b_is_constant:
        if series_a_clean.iloc[0] != series_b_clean.iloc[0]:
            # 不抛出异常，而是记录警告并返回None，避免中断批量计算
            logger.warning(
                f"序列A为常数 {series_a_clean.iloc[0]}，序列B为常数 {series_b_clean.iloc[0]}，KL散度为无穷"
            )
            raise ValueError(
                f"序列A和B为不同常数值，无法计算KL散度"
            )
        bins = 1
    elif series_a_is_constant or series_b_is_constant:
        bins = 1

    # 确定共同的分箱范围
    combined_min = min(series_a_clean.min(), series_b_clean.min())
    combined_max = max(series_a_clean.max(), series_b_clean.max())

    if combined_min == combined_max:
        # 所有数据点相同
        bin_edges = np.array([combined_min, combined_max + 1e-9])
        bins_actual = 1
    else:
        bin_edges = np.linspace(combined_min, combined_max, bins + 1)
        bins_actual = bins

    # 计算直方图（计数）
    counts_a, _ = np.histogram(series_a_clean, bins=bin_edges, density=False)
    counts_b, _ = np.histogram(series_b_clean, bins=bin_edges, density=False)

    # 转换为概率
    p = counts_a / counts_a.sum() if counts_a.sum() > 0 else np.zeros_like(counts_a, dtype=float)
    q = counts_b / counts_b.sum() if counts_b.sum() > 0 else np.zeros_like(counts_b, dtype=float)

    # 检查数据是否在分箱范围内（直接报错，不使用兼容回退）
    if p.sum() == 0 and series_a_clean.shape[0] > 0:
        raise ValueError(
            f"序列A数据不在分箱范围内（范围: [{combined_min:.4f}, {combined_max:.4f}]）"
        )

    if q.sum() == 0 and series_b_clean.shape[0] > 0:
        raise ValueError(
            f"序列B数据不在分箱范围内（范围: [{combined_min:.4f}, {combined_max:.4f}]）"
        )

    return p, q, bin_edges


def kl_divergence(
    p: np.ndarray,
    q: np.ndarray,
    smoothing_alpha: float = DEFAULT_KL_SMOOTHING_ALPHA
) -> float:
    """
    计算两个离散概率分布之间的KL散度

    D_KL(P || Q) = sum(P(i) * log(P(i) / Q(i)))

    Args:
        p: 第一个概率分布
        q: 第二个概率分布
        smoothing_alpha: Laplace平滑参数（避免log(0)）

    Returns:
        KL散度值

    Raises:
        ValueError: 当分布形状不匹配时
    """
    if p.shape != q.shape:
        raise ValueError(f"分布形状不匹配: p.shape={p.shape}, q.shape={q.shape}")

    # 归一化（处理浮点误差）
    if not np.isclose(p.sum(), 1.0, atol=1e-9):
        p = p / p.sum() if p.sum() != 0 else np.ones_like(p) / len(p)
    if not np.isclose(q.sum(), 1.0, atol=1e-9):
        q = q / q.sum() if q.sum() != 0 else np.ones_like(q) / len(q)

    # 应用对称平滑
    p_smooth = p + smoothing_alpha
    q_smooth = q + smoothing_alpha

    # 重新归一化
    p_smooth = p_smooth / p_smooth.sum()
    q_smooth = q_smooth / q_smooth.sum()

    # 计算KL散度（使用log差来提高数值稳定性）
    valid_indices = (p_smooth > 0) & (q_smooth > 0)

    if not np.any(valid_indices):
        logger.warning("没有有效的概率值，返回0散度")
        return 0.0

    p_valid = p_smooth[valid_indices]
    q_valid = q_smooth[valid_indices]

    log_ratio = np.log(p_valid) - np.log(q_valid)
    kl_value = np.sum(p_valid * log_ratio)

    # 处理数值问题
    if np.isnan(kl_value) or np.isinf(kl_value):
        # 截断极端值
        log_ratio_clipped = np.clip(log_ratio, -30, 30)
        kl_value = np.sum(p_valid * log_ratio_clipped)
        logger.warning(f"检测到NaN/Inf，使用截断值: {kl_value}")

    return max(0.0, kl_value)


def calculate_kl_divergence_series(
    series_a: pd.Series,
    series_b: pd.Series,
    bins: Optional[int] = None,
    smoothing_alpha: float = DEFAULT_KL_SMOOTHING_ALPHA,
    min_samples: Optional[int] = None
) -> Tuple[Optional[float], Optional[str]]:
    """
    计算两个序列之间的KL散度（一站式函数）

    Args:
        series_a: 第一个序列
        series_b: 第二个序列
        bins: 分箱数（None则使用Stata自动分箱算法）
        smoothing_alpha: 平滑参数
        min_samples: 最小样本数（None则使用默认值）

    Returns:
        Tuple[KL散度值, 错误消息（如果有）]
    """
    # 数据验证
    series_a_clean = series_a.dropna()
    series_b_clean = series_b.dropna()

    # 自动计算分箱数（用于确定最小样本数）
    if bins is None:
        n_samples = min(len(series_a_clean), len(series_b_clean))
        bins_for_validation = calculate_stata_bins(n_samples)
    else:
        bins_for_validation = bins

    if min_samples is None:
        min_samples = max(bins_for_validation * 2, MIN_SAMPLES_KL_DIVERGENCE)

    if len(series_a_clean) < min_samples:
        return None, f"序列A样本数不足: {len(series_a_clean)} < {min_samples}"

    if len(series_b_clean) < min_samples:
        return None, f"序列B样本数不足: {len(series_b_clean)} < {min_samples}"

    try:
        # 转换为分布
        p, q, _ = series_to_distribution(series_a_clean, series_b_clean, bins)

        # 计算KL散度
        kl_val = kl_divergence(p, q, smoothing_alpha)

        return kl_val, None

    except ValueError as ve:
        logger.warning(f"KL散度计算失败: {ve}")
        return np.inf, str(ve)

    except Exception as e:
        logger.error(f"KL散度计算出错: {e}")
        return np.inf, str(e)
