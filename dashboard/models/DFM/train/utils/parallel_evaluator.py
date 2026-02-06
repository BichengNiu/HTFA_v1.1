# -*- coding: utf-8 -*-
"""
并行变量评估器

提供变量选择过程中的并行评估功能，使用目标变量RMSE作为优化指标
"""

import logging
from typing import List, Tuple, Dict, Callable, Optional, Any

import pandas as pd

from dashboard.models.DFM.train.core.models import EvaluationConfig

logger = logging.getLogger(__name__)


def _build_temp_variables(var: str, current_variables: List[str]) -> List[str]:
    """构建移除变量后的临时变量列表"""
    return [v for v in current_variables if v != var]


def evaluate_single_variable_removal(
    var: str,
    current_variables: List[str],
    full_data: pd.DataFrame,
    k_factors: int,
    evaluator_config: Dict[str, Any]
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    评估移除单个变量后的模型性能

    Args:
        var: 待移除的变量名
        current_variables: 当前变量列表
        full_data: 完整数据DataFrame
        k_factors: 因子数
        evaluator_config: 评估器配置字典
            - training_start: 训练开始日期
            - train_end: 训练结束日期
            - validation_start: 验证开始日期
            - validation_end: 验证结束日期
            - max_iterations: 最大迭代次数
            - tolerance: 容差
            - training_weight: 训练期权重
            - factor_selection_method: 因子选择方法
            - pca_threshold: PCA阈值
            - kaiser_threshold: Kaiser阈值
            - target_variable: 目标变量

    Returns:
        (变量名, 评估结果字典) 或 (变量名, None) 如果评估失败
        结果字典包含: var, score (目标变量RMSE)
    """
    try:
        temp_variables = _build_temp_variables(var, current_variables)
        if not temp_variables:
            return (var, None)

        # 检查因子数约束
        if k_factors >= len(temp_variables):
            logger.debug(
                f"跳过'{var}': k_factors({k_factors}) >= 变量数({len(temp_variables)})"
            )
            return (var, None)

        from dashboard.models.DFM.train.training.evaluator_strategy import _evaluate_variable_selection_model

        # 验证必需的配置参数
        required_keys = ['training_start', 'train_end', 'validation_start',
                        'validation_end', 'max_iterations', 'tolerance',
                        'training_weight', 'factor_selection_method',
                        'pca_threshold', 'kaiser_threshold']
        for key in required_keys:
            if key not in evaluator_config:
                raise ValueError(f"evaluator_config缺少必需参数: {key}")

        # 构建 EvaluationConfig 并调用评估函数
        eval_config = EvaluationConfig(
            full_data=full_data,
            variables=temp_variables,
            k_factors=k_factors,
            factor_selection_method=evaluator_config['factor_selection_method'],
            pca_threshold=evaluator_config['pca_threshold'],
            kaiser_threshold=evaluator_config['kaiser_threshold'],
            training_start=evaluator_config['training_start'],
            train_end=evaluator_config['train_end'],
            max_iterations=evaluator_config['max_iterations'],
            tolerance=evaluator_config['tolerance'],
            validation_start=evaluator_config['validation_start'],
            validation_end=evaluator_config['validation_end'],
            training_weight=evaluator_config['training_weight'],
            target_variable=evaluator_config.get('target_variable')
        )

        score = _evaluate_variable_selection_model(eval_config)

        return (var, {
            'var': var,
            'score': score  # 目标变量RMSE，越小越好
        })

    except Exception as e:
        logger.exception(f"评估移除'{var}'时出错: {e}")
        return (var, None)


def evaluate_variable_removals(
    current_variables: List[str],
    candidate_vars: List[str],
    full_data: pd.DataFrame,
    k_factors: int,
    evaluator_config: Dict[str, Any],
    n_jobs: int = -1,
    backend: str = 'loky',
    verbose: int = 0,
    progress_callback: Optional[Callable[[str], None]] = None
) -> List[Dict[str, Any]]:
    """
    评估所有候选变量的移除效果

    Args:
        current_variables: 当前变量列表
        candidate_vars: 候选变量列表
        full_data: 完整数据DataFrame
        k_factors: 因子数
        evaluator_config: 评估器配置字典
        n_jobs: 并行任务数
        backend: 并行后端
        verbose: 是否显示进度
        progress_callback: 进度回调函数

    Returns:
        评估结果列表，每个结果包含 var 和 score
    """
    try:
        from joblib import Parallel, delayed
    except ImportError as e:
        raise ImportError("未安装joblib库，请安装: pip install joblib") from e

    n_candidates = len(candidate_vars)

    # RMSE标签
    rmse_label = "目标变量RMSE"

    if progress_callback:
        cores_desc = str(n_jobs) if n_jobs > 0 else 'all'
        progress_callback(
            f"  评估移除 {n_candidates} 个候选变量 "
            f"(n_jobs={cores_desc}, backend={backend})..."
        )

    results_with_none = Parallel(
        n_jobs=n_jobs,
        backend=backend,
        verbose=verbose,
        prefer='processes',
        batch_size='auto',
        pre_dispatch='2*n_jobs'
    )(
        delayed(evaluate_single_variable_removal)(
            var,
            current_variables,
            full_data,
            k_factors,
            evaluator_config
        )
        for var in candidate_vars
    )

    candidate_results = []
    for idx, (var, result) in enumerate(results_with_none, 1):
        if result is None:
            continue

        if progress_callback:
            progress_callback(
                f"  [{idx}/{n_candidates}] '{var}' - {rmse_label}: {result['score']:.4f}"
            )

        candidate_results.append(result)

    return candidate_results


__all__ = [
    'evaluate_single_variable_removal',
    'evaluate_variable_removals',
]
