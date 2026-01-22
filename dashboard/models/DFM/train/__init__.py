# -*- coding: utf-8 -*-
"""
DFM训练模块 - 重构版本
基于KISS, DRY, YAGNI, SOC, SRP原则的全新架构

主要组件：
- DFMTrainer: 统一训练接口（完整两阶段训练流程）
- TrainingConfig: 扁平化配置管理
- DFMModel: 核心DFM算法实现
- KalmanFilter: 卡尔曼滤波和平滑
- BackwardSelector: 后向逐步变量选择
"""

# 主训练器和配置
from dashboard.models.DFM.train.training.trainer import DFMTrainer
from dashboard.models.DFM.train.training.config import TrainingConfig

# 核心模型（统一数据类）
from dashboard.models.DFM.train.core.models import (
    TrainingResult,
    EvaluationMetrics,
    DFMModelResult,
    SelectionResult,
    KalmanFilterResult,
    KalmanSmootherResult,
    MetricsResult
)

# 核心算法
from dashboard.models.DFM.train.core.factor_model import DFMModel
from dashboard.models.DFM.train.core.kalman import KalmanFilter
from dashboard.models.DFM.train.core.prediction import generate_target_forecast

# 评估指标
from dashboard.models.DFM.train.evaluation.metrics import (
    calculate_rmse,
    calculate_aligned_win_rate
)

# 变量选择
from dashboard.models.DFM.train.selection.backward_selector import BackwardSelector

# 结果导出
from dashboard.models.DFM.train.export.exporter import TrainingResultExporter

# 环境配置
from dashboard.models.DFM.train.utils.environment import setup_training_environment

__version__ = '2.0.0-refactored'

__all__ = [
    # ============ 主要API（用户常用） ============
    'DFMTrainer',           # 训练器
    'TrainingConfig',       # 配置类
    'TrainingResult',       # 训练结果
    'EvaluationMetrics',    # 评估指标

    # ============ 高级API（进阶使用） ============
    # 如需使用以下组件，可从子模块显式导入：
    # from dashboard.models.DFM.train.core import DFMModel, KalmanFilter
    # from dashboard.models.DFM.train.selection import BackwardSelector
    # from dashboard.models.DFM.train.export import TrainingResultExporter

    # 数据模型（仅导出常用的，其他按需从子模块导入）
    'DFMModelResult',       # DFM模型结果

    # 核心算法（仅导出最常用的）
    'DFMModel',             # DFM模型类

    # 结果导出
    'TrainingResultExporter',  # 结果导出器
]
