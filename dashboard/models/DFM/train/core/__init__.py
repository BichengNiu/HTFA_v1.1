# -*- coding: utf-8 -*-
"""
核心算法层

包含DFM模型的核心算法实现：
- models: 统一数据模型
- kalman: 卡尔曼滤波器
- factor_model: DFM主算法
- estimator: 参数估计
- validation: 数据验证工具
"""

# 数据模型
from dashboard.models.DFM.train.core.models import (
    EvaluationMetrics,
    DFMModelResult,
    TrainingResult
)

# 卡尔曼滤波
from dashboard.models.DFM.train.core.kalman import KalmanFilter

# DFM模型
from dashboard.models.DFM.train.core.factor_model import DFMModel

# 参数估计
from dashboard.models.DFM.train.core.estimator import estimate_loadings

# PCA工具
from dashboard.models.DFM.train.core.pca_utils import select_num_factors

# 验证工具
from dashboard.models.DFM.train.core.validation import (
    validate_matrix,
    validate_matrices,
)

__all__ = [
    # 数据模型
    'EvaluationMetrics',
    'DFMModelResult',
    'TrainingResult',

    # 算法组件
    'KalmanFilter',
    'DFMModel',
    'estimate_loadings',
    'select_num_factors',

    # 验证工具
    'validate_matrix',
    'validate_matrices',
]
