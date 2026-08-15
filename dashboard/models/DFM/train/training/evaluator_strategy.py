# -*- coding: utf-8 -*-
"""
DFM评估策略 - 函数式接口

提供简洁的函数式接口创建DFM评估器，使用目标变量RMSE作为评估指标

重构说明:
- 将闭包函数改为模块级顶层函数,解决pickle序列化问题
- 通过参数显式传递config数据,而非闭包捕获
- 保持API兼容性
- 使用EvaluationConfig封装参数，减少函数参数数量
"""

import numpy as np
import pandas as pd
from typing import List, Callable, Dict
from dashboard.models.DFM.train.utils.logger import get_logger
from dashboard.models.DFM.train.training.config import TrainingConfig
from dashboard.models.DFM.train.training.model_ops import train_dfm_model, evaluate_model_fit
from dashboard.models.DFM.train.core.pca_utils import compute_optimal_k_factors
from dashboard.models.DFM.train.core.models import EvaluationConfig

logger = get_logger(__name__)


def build_evaluation_config(
    *,
    full_data: pd.DataFrame,
    variables: List[str],
    k_factors: int,
    settings: Dict,
) -> EvaluationConfig:
    """从统一设置字典构建串行和并行共用的评估配置。"""
    required = (
        "training_start",
        "train_end",
        "validation_start",
        "validation_end",
        "max_iterations",
        "tolerance",
        "training_weight",
        "factor_selection_method",
        "pca_threshold",
        "kaiser_threshold",
    )
    missing = [key for key in required if key not in settings]
    if missing:
        raise ValueError(f"评估配置缺少必需参数: {missing}")
    return EvaluationConfig(
        full_data=full_data,
        variables=variables,
        k_factors=k_factors,
        factor_selection_method=settings["factor_selection_method"],
        pca_threshold=settings["pca_threshold"],
        kaiser_threshold=settings["kaiser_threshold"],
        training_start=settings["training_start"],
        train_end=settings["train_end"],
        max_iterations=settings["max_iterations"],
        tolerance=settings["tolerance"],
        validation_start=settings["validation_start"],
        validation_end=settings["validation_end"],
        training_weight=settings["training_weight"],
        target_variable=settings.get("target_variable"),
    )


# ========== 可序列化的顶层评估函数 ==========

def _evaluate_variable_selection_model(config: EvaluationConfig) -> float:
    """
    顶层变量选择评估函数（可序列化，支持动态因子数）

    Args:
        config: EvaluationConfig 评估配置对象，包含所有必需参数

    Returns:
        float: 加权目标变量RMSE（越小越好）

    Note:
        当factor_selection_method!='fixed'时，会基于当前变量集动态计算最优k_factors。
        这确保了变量选择过程中每次评估都使用最优的因子数。
    """
    try:
        if len(config.variables) == 0:
            logger.warning("[VarSelectionEvaluator] 变量为空，返回最差得分")
            return np.inf

        # 动态计算因子数
        if config.factor_selection_method != 'fixed':
            k_factors_effective = compute_optimal_k_factors(
                data=config.full_data,
                variables=config.variables,
                method=config.factor_selection_method,
                fixed_k=config.k_factors,
                pca_threshold=config.pca_threshold,
                kaiser_threshold=config.kaiser_threshold,
                train_end=config.train_end
            )
        else:
            k_factors_effective = config.k_factors

        # 检查因子数约束
        if k_factors_effective >= len(config.variables):
            k_factors_effective = max(1, len(config.variables) - 1)
            logger.debug(f"[VarSelectionEvaluator] 调整因子数为 {k_factors_effective}")

        # 准备数据
        observation_data = config.full_data[config.variables]

        # 训练模型
        model_result = train_dfm_model(
            observation_data=observation_data,
            k_factors=k_factors_effective,
            training_start=config.training_start,
            train_end=config.train_end,
            max_iter=config.max_iterations,
            max_lags=1,
            tolerance=config.tolerance,
            progress_callback=None
        )

        # 评估模型拟合质量
        metrics = evaluate_model_fit(
            model_result=model_result,
            observation_data=observation_data,
            training_start=config.training_start,
            train_end=config.train_end,
            validation_start=config.validation_start,
            validation_end=config.validation_end,
            training_weight=config.training_weight,
            target_variable=config.target_variable,
            variable_names=config.variables
        )

        # 返回目标变量RMSE
        return metrics.weighted_target_rmse

    except Exception as e:
        logger.exception(f"[VarSelectionEvaluator] 评估失败: {e}")
        return np.inf


# ========== 工厂函数（返回可调用对象） ==========

def create_variable_selection_evaluator(config: TrainingConfig) -> Callable:
    """
    创建变量筛选专用评估器（函数式接口）

    使用加权目标变量RMSE作为评估指标（越小越好），专门用于变量筛选阶段。

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
                - params: Dict (必须包含 k_factors, validation_start, validation_end)
                - max_iter: int (可选，默认使用config.max_iterations)

        Returns:
            float: 加权RMSE（越小越好）
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

        eval_config = build_evaluation_config(
            full_data=full_data,
            variables=variables,
            k_factors=params['k_factors'],
            settings={
                "factor_selection_method": params.get(
                    "factor_selection_method", config.factor_selection_method
                ),
                "pca_threshold": params.get("pca_threshold", config.pca_threshold),
                "kaiser_threshold": params.get(
                    "kaiser_threshold", config.kaiser_threshold
                ),
                "training_start": config.training_start,
                "train_end": config.train_end,
                "max_iterations": kwargs.get("max_iter", config.max_iterations),
                "tolerance": config.tolerance,
                "validation_start": params.get(
                    "validation_start", config.validation_start
                ),
                "validation_end": params.get(
                    "validation_end", config.validation_end
                ),
                "training_weight": params.get("training_weight", 0.5),
                "target_variable": params.get(
                    "target_variable", config.target_variable
                ),
            },
        )

        # 调用可序列化的顶层函数
        return _evaluate_variable_selection_model(eval_config)

    return evaluate


__all__ = [
    'create_variable_selection_evaluator',
    '_evaluate_variable_selection_model',
    'build_evaluation_config',
    'EvaluationConfig',
]
