# -*- coding: utf-8 -*-
"""
DFM评估策略 - 函数式接口

提供简洁的函数式接口创建DFM评估器

重构说明:
- 将闭包函数改为模块级顶层函数,解决pickle序列化问题
- 通过参数显式传递config数据,而非闭包捕获
- 保持API兼容性
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Callable, Dict, Any
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.training.model_ops import train_dfm_with_forecast, evaluate_model_performance
from dashboard.models.DFM.train.core.pca_utils import compute_optimal_k_factors

logger = get_logger(__name__)


# ========== 可序列化的顶层评估函数 ==========

def _evaluate_variable_selection_model(
    variables: List[str],
    target_variable: str,
    full_data: pd.DataFrame,
    k_factors: int,
    training_start: str,
    train_end: str,
    validation_start: str,
    validation_end: str,
    max_iterations: int,
    tolerance: float,
    alignment_mode: str = 'next_month',
    factor_selection_method: str = 'fixed',
    pca_threshold: float = 0.9,
    kaiser_threshold: float = 1.0
) -> Tuple[float, float, float, float, float, float, bool, None, None]:
    """
    顶层变量选择评估函数（可序列化，支持动态因子数）

    Args:
        variables: 变量列表（包含目标变量）
        target_variable: 目标变量名
        full_data: 完整数据DataFrame
        k_factors: 因子数（fixed模式使用，或作为动态模式的fallback）
        training_start: 训练开始日期
        train_end: 训练结束日期
        validation_start: 验证开始日期
        validation_end: 验证结束日期
        max_iterations: 最大迭代次数
        tolerance: 容差
        alignment_mode: 目标配对模式 ('current_month' 或 'next_month')
        factor_selection_method: 因子选择方法 ('fixed', 'cumulative', 'kaiser')
        pca_threshold: PCA累积方差阈值（method='cumulative'时使用）
        kaiser_threshold: Kaiser特征值阈值（method='kaiser'时使用）

    Returns:
        9元组: (is_rmse, oos_rmse, None, None, is_win_rate, oos_win_rate, is_svd_error, None, None)

    Note:
        当factor_selection_method!='fixed'时，会基于当前变量集动态计算最优k_factors。
        这确保了变量选择过程中每次评估都使用最优的因子数。
    """
    try:
        # 分离预测变量
        predictor_vars = [v for v in variables if v != target_variable]

        if len(predictor_vars) == 0:
            logger.warning("[VarSelectionEvaluator] 预测变量为空，返回无穷大RMSE")
            return (np.inf, np.inf, np.nan, np.nan, np.nan, np.nan, False, None, None)

        # 动态计算因子数（新增逻辑）
        if factor_selection_method != 'fixed':
            k_factors_effective = compute_optimal_k_factors(
                data=full_data,
                variables=predictor_vars,
                method=factor_selection_method,
                fixed_k=k_factors,
                pca_threshold=pca_threshold,
                kaiser_threshold=kaiser_threshold,
                train_end=train_end
            )
        else:
            k_factors_effective = k_factors

        # 准备数据
        predictor_data = full_data[predictor_vars]
        target_data = full_data[target_variable]

        # 训练模型（使用有效的k_factors）
        model_result = train_dfm_with_forecast(
            predictor_data=predictor_data,
            target_data=target_data,
            k_factors=k_factors_effective,
            training_start=training_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            max_iter=max_iterations,
            max_lags=1,
            tolerance=tolerance,
            progress_callback=None
        )

        # 导入评估函数
        from dashboard.models.DFM.train.evaluation.metrics import (
            calculate_aligned_rmse,
            calculate_aligned_win_rate
        )

        # 训练期评估
        is_rmse = np.inf
        is_win_rate = np.nan
        if model_result.forecast_is is not None and len(model_result.forecast_is) > 0:
            train_data_len = len(model_result.forecast_is)
            train_index = pd.to_datetime(predictor_data.index[:train_data_len])
            train_nowcast = pd.Series(
                model_result.forecast_is,
                index=train_index
            )
            is_rmse = calculate_aligned_rmse(train_nowcast, target_data, alignment_mode)
            is_win_rate = calculate_aligned_win_rate(train_nowcast, target_data, alignment_mode)

        # 观察期评估
        oos_rmse = np.inf
        oos_win_rate = np.nan
        if model_result.forecast_oos is not None and len(model_result.forecast_oos) > 0:
            train_data_len = len(model_result.forecast_is) if model_result.forecast_is is not None else 0
            val_index = pd.to_datetime(predictor_data.index[train_data_len:train_data_len+len(model_result.forecast_oos)])

            if len(val_index) == len(model_result.forecast_oos):
                val_nowcast = pd.Series(
                    model_result.forecast_oos,
                    index=val_index
                )
                oos_rmse = calculate_aligned_rmse(val_nowcast, target_data, alignment_mode)
                oos_win_rate = calculate_aligned_win_rate(val_nowcast, target_data, alignment_mode)
            else:
                logger.warning(f"[VarSelectionEvaluator] 验证期索引长度不匹配: {len(val_index)} vs {len(model_result.forecast_oos)}")

        # 返回9元组（位置[4]和[5]为Win Rate）
        return (is_rmse, oos_rmse, np.nan, np.nan, is_win_rate, oos_win_rate, False, None, None)

    except Exception as e:
        logger.exception(f"[VarSelectionEvaluator] 评估失败: {e}")
        return (np.inf, np.inf, np.nan, np.nan, np.nan, np.nan, True, None, None)


# ========== 工厂函数（返回可调用对象） ==========

def create_variable_selection_evaluator(config: 'TrainingConfig') -> Callable:
    """
    创建变量筛选专用评估器（函数式接口）

    与create_dfm_evaluator的区别：
    - 使用下月配对RMSE作为唯一评估指标
    - 不计算Hit Rate和MAE（用于最终评估）
    - 专门用于变量筛选阶段

    重构后：返回一个lambda包装器，调用可序列化的顶层函数。

    Returns:
        评估函数，签名为 (variables: List[str], **kwargs) -> Tuple[float, ...]
    """
    def evaluate(variables: List[str], **kwargs) -> Tuple[float, float, float, float, float, float, bool, None, None]:
        """
        评估指定变量组合的DFM模型性能（仅使用下月配对RMSE）

        Args:
            variables: 变量列表（包含目标变量）
            **kwargs: 必需参数
                - full_data: pd.DataFrame
                - params: Dict (必须包含 k_factors)
                - max_iter: int (可选，默认使用config.max_iterations)

        Returns:
            9元组: (is_rmse, oos_rmse, None, None, is_win_rate, oos_win_rate, is_svd_error, None, None)
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
            target_variable=config.target_variable,
            full_data=full_data,
            k_factors=k_factors,
            training_start=config.training_start,
            train_end=config.train_end,
            validation_start=config.validation_start,
            validation_end=config.validation_end,
            max_iterations=max_iterations,
            tolerance=config.tolerance
        )

    return evaluate


__all__ = [
    'create_variable_selection_evaluator',
    '_evaluate_variable_selection_model',
]
