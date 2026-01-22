# -*- coding: utf-8 -*-
"""
训练协调层 - 重构版

训练流程管理和配置：
- trainer: DFMTrainer训练器（轻量级协调器）
- config: TrainingConfig配置管理（扁平化结构）
- model_ops: 统一的训练和评估操作（合并原model_trainer和model_evaluator）
- evaluator_strategy: DFM评估策略（函数式接口）
"""

from dashboard.models.DFM.train.training.trainer import DFMTrainer
from dashboard.models.DFM.train.training.config import TrainingConfig
from dashboard.models.DFM.train.training.model_ops import train_dfm_with_forecast, evaluate_model_performance
from dashboard.models.DFM.train.core.models import (
    EvaluationMetrics,
    DFMModelResult,
    TrainingResult
)

__all__ = [
    # 主要API
    'DFMTrainer',
    'TrainingConfig',

    # 模型操作
    'train_dfm_with_forecast',
    'evaluate_model_performance',

    # 数据模型
    'EvaluationMetrics',
    'DFMModelResult',
    'TrainingResult',
]
