# -*- coding: utf-8 -*-
"""
DFM评估策略 - 函数式接口

提供简洁的函数式接口创建DFM评估器
经典DFM模型：所有变量平等参与因子提取，无目标变量概念

重构说明:
- 将闭包函数改为模块级顶层函数,解决pickle序列化问题
- 通过参数显式传递config数据,而非闭包捕获
- 保持API兼容性
- 使用重构RMSE作为唯一评估标准（越小越好）
"""

import numpy as np
import pandas as pd
from typing import List, Callable, Dict
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.training.model_ops import train_dfm_model, evaluate_model_fit
from dashboard.models.DFM.train.core.pca_utils import compute_optimal_k_factors

logger = get_logger(__name__)


# ========== 可序列化的顶层评估函数 ==========

def _evaluate_variable_selection_model(
    variables: List[str],
    full_data: pd.DataFrame,
    k_factors: int,
    training_start: str,
    train_end: str,
    max_iterations: int,
    tolerance: float,
    factor_selection_method: str = 'fixed',
    pca_threshold: float = 0.9,
    kaiser_threshold: float = 1.0
) -> float:
    """
    顶层变量选择评估函数（可序列化，支持动态因子数）

    Args:
        variables: 变量列表
        full_data: 完整数据DataFrame
        k_factors: 因子数（fixed模式使用，或作为动态模式的fallback）
        training_start: 训练开始日期
        train_end: 训练结束日期
        max_iterations: 最大迭代次数
        tolerance: 容差
        factor_selection_method: 因子选择方法 ('fixed', 'cumulative', 'kaiser')
        pca_threshold: PCA累积方差阈值（method='cumulative'时使用）
        kaiser_threshold: Kaiser特征值阈值（method='kaiser'时使用）

    Returns:
        float: 重构RMSE（越小越好）

    Note:
        当factor_selection_method!='fixed'时，会基于当前变量集动态计算最优k_factors。
        这确保了变量选择过程中每次评估都使用最优的因子数。
    """
    try:
        if len(variables) == 0:
            logger.warning("[VarSelectionEvaluator] 变量为空，返回最差得分")
            return np.inf

        # 动态计算因子数
        if factor_selection_method != 'fixed':
            k_factors_effective = compute_optimal_k_factors(
                data=full_data,
                variables=variables,
                method=factor_selection_method,
                fixed_k=k_factors,
                pca_threshold=pca_threshold,
                kaiser_threshold=kaiser_threshold,
                train_end=train_end
            )
        else:
            k_factors_effective = k_factors

        # 检查因子数约束
        if k_factors_effective >= len(variables):
            k_factors_effective = max(1, len(variables) - 1)
            logger.debug(f"[VarSelectionEvaluator] 调整因子数为 {k_factors_effective}")

        # 准备数据
        observation_data = full_data[variables]

        # 训练模型
        model_result = train_dfm_model(
            observation_data=observation_data,
            k_factors=k_factors_effective,
            training_start=training_start,
            train_end=train_end,
            max_iter=max_iterations,
            max_lags=1,
            tolerance=tolerance,
            progress_callback=None
        )

        # 评估模型拟合质量
        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=observation_data,
            training_start=training_start,
            train_end=train_end
        )

        # 返回重构RMSE（越小越好）
        return metrics.reconstruction_rmse

    except Exception as e:
        logger.exception(f"[VarSelectionEvaluator] 评估失败: {e}")
        return np.inf


# ========== 工厂函数（返回可调用对象） ==========

def create_variable_selection_evaluator(config: 'TrainingConfig') -> Callable:
    """
    创建变量筛选专用评估器（函数式接口）

    使用重构RMSE作为评估指标（越小越好），专门用于变量筛选阶段。

    重构后：返回一个lambda包装器，调用可序列化的顶层函数。

    Returns:
        评估函数，签名为 (variables: List[str], **kwargs) -> float
    """
    def evaluate(variables: List[str], **kwargs) -> float:
        """
        评估指定变量组合的DFM模型性能

        Args:
            variables: 变量列表
            **kwargs: 必需参数
                - full_data: pd.DataFrame
                - params: Dict (必须包含 k_factors)
                - max_iter: int (可选，默认使用config.max_iterations)

        Returns:
            float: 重构RMSE（越小越好）
        """
        # 验证必需参数
        full_data = kwargs.get('full_data')
        if full_data is None:
            raise ValueError("evaluate()缺少必需参数: full_data")

        params = kwargs.get('params')
        if params is None:
            raise ValueError("evaluate()缺少必需参数: params")

        if 'k_factors' not in params:
            raise ValueError("params必须包含k_factors")

        k_factors = params['k_factors']
        max_iterations = kwargs.get('max_iter', config.max_iterations)

        # 调用可序列化的顶层函数
        return _evaluate_variable_selection_model(
            variables=variables,
            full_data=full_data,
            k_factors=k_factors,
            training_start=config.training_start,
            train_end=config.train_end,
            max_iterations=max_iterations,
            tolerance=config.tolerance,
            factor_selection_method=params.get('factor_selection_method', config.factor_selection_method),
            pca_threshold=params.get('pca_threshold', config.pca_threshold),
            kaiser_threshold=params.get('kaiser_threshold', config.kaiser_threshold)
        )

    return evaluate


__all__ = [
    'create_variable_selection_evaluator',
    '_evaluate_variable_selection_model',
]
