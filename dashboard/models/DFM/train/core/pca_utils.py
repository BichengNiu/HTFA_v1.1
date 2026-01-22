# -*- coding: utf-8 -*-
"""
PCA工具模块

提供因子数选择相关的PCA分析功能
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Dict
from sklearn.decomposition import PCA
from dashboard.models.DFM.train.utils.logger import get_logger

logger = get_logger(__name__)


def select_num_factors(
    data: pd.DataFrame,
    selected_vars: List[str],
    method: str,
    fixed_k: int,
    pca_threshold: float = 0.9,
    elbow_threshold: float = 0.1,
    kaiser_threshold: float = 1.0,
    train_end: Optional[str] = None
) -> Tuple[int, Optional[Dict]]:
    """
    因子数选择

    支持四种方法：
    1. fixed: 固定因子数
    2. cumulative: PCA累积方差贡献率
    3. elbow: Elbow方法（边际方差阈值）
    4. kaiser: Kaiser准则（特征值>阈值）

    Args:
        data: 完整数据 (DataFrame)
        selected_vars: 选中的变量列表
        method: 选择方法 ('fixed', 'cumulative', 'elbow', 'kaiser')
        fixed_k: 固定因子数（method='fixed'时使用）
        pca_threshold: PCA累积方差阈值（method='cumulative'时使用，默认0.9）
        elbow_threshold: Elbow边际方差阈值（method='elbow'时使用，默认0.1）
        kaiser_threshold: Kaiser特征值阈值（method='kaiser'时使用，默认1.0）
        train_end: 训练集结束日期（用于标准化参数计算，避免数据泄露）

    Returns:
        (k_factors, pca_analysis):
            - k_factors: 选定的因子数
            - pca_analysis: PCA分析结果字典（包含explained_variance, cumsum_variance, eigenvalues）

    Raises:
        ValueError: 如果method不在支持的方法中

    Examples:
        >>> # 固定因子数
        >>> k, _ = select_num_factors(data, vars, 'fixed', fixed_k=3)

        >>> # PCA累积方差
        >>> k, analysis = select_num_factors(
        ...     data, vars, 'cumulative',
        ...     fixed_k=None, pca_threshold=0.85
        ... )
        >>> print(f"选定因子数: {k}, 累积方差: {analysis['cumsum_variance'][k-1]:.1%}")

        >>> # Kaiser准则
        >>> k, analysis = select_num_factors(
        ...     data, vars, 'kaiser',
        ...     fixed_k=None, kaiser_threshold=1.0
        ... )
    """
    logger.info("=" * 60)
    logger.info("因子数选择")
    logger.info("=" * 60)

    # 步骤1: 数据标准化（避免数据泄露，仅使用训练集计算标准化参数）
    data_subset = data[selected_vars].copy()

    if train_end is not None:
        # 使用训练集数据计算标准化参数
        try:
            train_data = data_subset.loc[:train_end]
            global_mean = train_data.mean(axis=0)
            global_std = train_data.std(axis=0)
            logger.info(f"使用训练集数据计算标准化参数 (截止到 {train_end}, {len(train_data)} 样本)")
        except (KeyError, IndexError) as e:
            raise ValueError(f"无法提取训练集进行标准化: {e}，请检查train_end参数是否在数据索引范围内")
    else:
        raise ValueError(
            "train_end参数必须提供以避免数据泄露。"
            "PCA分析必须仅使用训练期数据计算标准化参数。"
        )

    # 处理标准差为0的列（避免除零错误）
    zero_std_cols = global_std[global_std == 0].index.tolist()
    if zero_std_cols:
        logger.warning(f"以下列标准差为0，将被移除: {zero_std_cols}")
        data_subset = data_subset.drop(columns=zero_std_cols)
        global_mean = global_mean.drop(labels=zero_std_cols)
        global_std = global_std.drop(labels=zero_std_cols)

    # 应用标准化
    data_standardized = (data_subset - global_mean) / global_std
    logger.info(f"数据标准化完成. Shape: {data_standardized.shape}")

    # 步骤2: 填充NaN
    data_for_pca = data_standardized.fillna(0)

    # 步骤3: 执行PCA分析（仅在训练期数据上拟合，避免数据泄露）
    logger.info(f"执行PCA分析 (method={method})...")
    pca = PCA()

    # 仅在训练期数据上拟合PCA，避免验证期/观察期数据泄露
    data_for_pca_train = data_standardized.loc[:train_end].fillna(0)
    pca.fit(data_for_pca_train)
    logger.info(f"PCA仅在训练期数据上拟合 ({len(data_for_pca_train)} 样本)")

    explained_variance = pca.explained_variance_ratio_
    cumsum_variance = np.cumsum(explained_variance)

    pca_analysis = {
        'explained_variance': explained_variance,
        'cumsum_variance': cumsum_variance,
        'eigenvalues': pca.explained_variance_
    }

    # 获取实际可用的主成分数量
    max_components = len(explained_variance)
    logger.info(f"实际可提取的主成分数量: {max_components}")

    # 方法1: 固定因子数
    if method == 'fixed':
        k = fixed_k
        # 验证fixed_k是否超过实际可用的主成分数量
        if k > max_components:
            raise ValueError(
                f"固定因子数k={k}超过实际可提取的主成分数量{max_components}。"
                f"请减少k_factors或增加变量数量。"
            )

        logger.info(f"使用固定因子数: k={k}")
        if k > 0 and k <= len(cumsum_variance):
            logger.info(f"对应累积方差: {cumsum_variance[k-1]:.1%}")
        return k, pca_analysis

    # 方法2: 累积方差贡献率
    if method == 'cumulative':
        indices = np.where(cumsum_variance >= pca_threshold)[0]
        if len(indices) == 0:
            raise ValueError(
                f"PCA累积方差未达到阈值{pca_threshold:.1%}，"
                f"最大累积方差为{cumsum_variance[-1]:.1%}。"
                f"请降低pca_threshold或增加变量数量。"
            )
        else:
            k = indices[0] + 1
        logger.info(
            f"PCA累积方差方法: 阈值={pca_threshold:.1%}, k={k}, "
            f"累积方差={cumsum_variance[k-1]:.1%}"
        )

    # 方法3: Elbow方法
    elif method == 'elbow':
        marginal_variance = np.diff(explained_variance)
        indices = np.where(marginal_variance < elbow_threshold)[0]
        if len(indices) == 0:
            raise ValueError(
                f"Elbow方法未找到拐点(阈值={elbow_threshold:.1%})。"
                f"请调整elbow_threshold或使用其他因子选择方法。"
            )
        else:
            k = indices[0] + 1
        logger.info(f"Elbow方法: 阈值={elbow_threshold:.1%}, k={k}")

    # 方法4: Kaiser准则（特征值>阈值）
    elif method == 'kaiser':
        eigenvalues = pca.explained_variance_
        k = np.sum(eigenvalues > kaiser_threshold)
        if k == 0:
            raise ValueError(
                f"Kaiser准则: 没有特征值大于{kaiser_threshold}。"
                f"请降低kaiser_threshold或使用其他因子选择方法。"
            )
        else:
            logger.info(f"Kaiser准则: 阈值={kaiser_threshold}, k={k}")
            logger.info(f"特征值分布: {eigenvalues[:min(10, len(eigenvalues))]}")

    else:
        raise ValueError(f"未知的因子选择方法: {method}")

    # 确保k在合理范围内
    k = max(1, min(k, len(selected_vars) - 1))
    logger.info(f"因子数选择完成: k={k}")

    return k, pca_analysis


def compute_optimal_k_factors(
    data: pd.DataFrame,
    variables: List[str],
    method: str,
    fixed_k: int,
    pca_threshold: float = 0.9,
    kaiser_threshold: float = 1.0,
    train_end: Optional[str] = None
) -> int:
    """
    计算最优因子数（用于变量选择过程中动态计算）

    轻量级接口，在变量选择过程中快速计算k_factors。

    Args:
        data: 完整数据DataFrame
        variables: 当前变量列表（预测变量）
        method: 选择方法 ('fixed', 'cumulative', 'kaiser')
        fixed_k: 固定因子数（method='fixed'时使用）
        pca_threshold: PCA累积方差阈值（method='cumulative'时使用，默认0.9）
        kaiser_threshold: Kaiser特征值阈值（method='kaiser'时使用，默认1.0）
        train_end: 训练期结束日期（用于避免数据泄露）

    Returns:
        k_factors: 计算得到的因子数

    Raises:
        ValueError: 如果输入参数无效

    Examples:
        >>> # fixed模式直接返回
        >>> k = compute_optimal_k_factors(data, vars, 'fixed', fixed_k=5)

        >>> # cumulative模式动态计算
        >>> k = compute_optimal_k_factors(
        ...     data, vars, 'cumulative',
        ...     fixed_k=5, pca_threshold=0.85
        ... )
    """
    # 输入验证
    if not variables:
        raise ValueError("变量列表不能为空")

    if fixed_k < 1:
        raise ValueError(f"fixed_k必须>=1，当前值: {fixed_k}")

    if method not in ['fixed', 'cumulative', 'kaiser', 'elbow']:
        raise ValueError(f"无效的方法: {method}，必须是'fixed', 'cumulative', 'kaiser'或'elbow'之一")

    n_vars = len(variables)
    max_k = n_vars - 1

    # fixed模式快速路径
    if method == 'fixed':
        return min(fixed_k, max_k)

    # 变量数过少时使用固定值（避免PCA不稳定）
    if n_vars < 5:
        k = min(fixed_k, max(1, max_k))
        logger.debug(
            f"[DynamicK] 变量数{n_vars}<5，使用固定k={k}"
        )
        return k

    # 调用完整PCA分析（静默模式）
    k, _ = select_num_factors(
        data=data,
        selected_vars=variables,
        method=method,
        fixed_k=fixed_k,
        pca_threshold=pca_threshold,
        kaiser_threshold=kaiser_threshold,
        train_end=train_end
    )

    logger.debug(
        f"[DynamicK] 变量数={len(variables)}, method={method}, k={k}"
    )

    return k


__all__ = ['select_num_factors', 'compute_optimal_k_factors']
