# -*- coding: utf-8 -*-
"""
UI配置管理
统一管理所有UI相关的配置和默认值
"""

from datetime import date
from typing import Dict
import pandas as pd


class UIConfig:
    """UI配置类 - 单一配置来源"""

    # 日期默认值
    DEFAULT_TRAINING_START = date(2020, 1, 1)
    DEFAULT_VALIDATION_START = date(2025, 4, 1)  # 验证期开始日期，至少在观察期开始前3个月
    DEFAULT_OBSERVATION_START = date(2025, 7, 1)  # 观察期开始日期（DDFM模式使用）

    # 因子选择策略
    FACTOR_STRATEGIES = {
        'fixed_number': "固定因子数 (默认)",
        'cumulative_variance': "累积方差贡献",
        'kaiser': "Kaiser准则 (特征值>1)"
    }
    DEFAULT_FACTOR_STRATEGY = 'kaiser'

    # 因子数配置
    DEFAULT_K_FACTORS = 4
    K_FACTORS_MIN = 1
    K_FACTORS_MAX = 15

    # 累积方差配置
    DEFAULT_CUM_VARIANCE = 0.8
    CUM_VARIANCE_MIN = 0.5
    CUM_VARIANCE_MAX = 0.99
    CUM_VARIANCE_STEP = 0.01

    # Kaiser准则配置
    DEFAULT_KAISER_THRESHOLD = 1.0
    KAISER_THRESHOLD_MIN = 0.5
    KAISER_THRESHOLD_MAX = 2.0
    KAISER_THRESHOLD_STEP = 0.1

    # 目标变量配置 (2026-01新增)
    TARGET_VARIABLE_HELP = "选择目标变量（必选），将以该变量为最小化RMSE的目标"

    # ========== 算法选择配置（2025-12-21新增）==========
    ALGORITHM_OPTIONS = {
        'classical': '经典DFM (EM算法)',
        'deep_learning': '深度学习DFM (DDFM)'
    }
    DEFAULT_ALGORITHM = 'classical'

    # ========== DDFM专用参数配置 ==========
    # 编码器结构
    ENCODER_STRUCTURE_DEFAULT = "16, 4"  # 默认编码器结构字符串
    ENCODER_STRUCTURE_HELP = "逗号分隔的神经元数，最后一个数为因子数。如'16, 4'表示两层网络，最终4个因子"

    # 学习率
    LEARNING_RATE_DEFAULT = 0.005
    LEARNING_RATE_MIN = 0.0001
    LEARNING_RATE_MAX = 0.1
    LEARNING_RATE_STEP = 0.0001

    # MCMC迭代
    MCMC_MAX_ITER_DEFAULT = 200
    MCMC_MAX_ITER_MIN = 50
    MCMC_MAX_ITER_MAX = 500
    MCMC_MAX_ITER_STEP = 10

    # 批量大小
    BATCH_SIZE_DEFAULT = 100
    BATCH_SIZE_MIN = 16
    BATCH_SIZE_MAX = 512
    BATCH_SIZE_STEP = 16

    # 每次MCMC的epoch数
    EPOCHS_PER_MCMC_DEFAULT = 100
    EPOCHS_PER_MCMC_MIN = 10
    EPOCHS_PER_MCMC_MAX = 500
    EPOCHS_PER_MCMC_STEP = 10

    # MCMC收敛阈值
    MCMC_TOLERANCE_DEFAULT = 0.0005
    MCMC_TOLERANCE_MIN = 0.00001
    MCMC_TOLERANCE_MAX = 0.01

    # 因子AR阶数（DDFM专用）
    DDFM_FACTOR_ORDER_OPTIONS = {
        1: "AR(1)",
        2: "AR(2)"
    }
    DDFM_FACTOR_ORDER_DEFAULT = 2

    # 优化器选项
    DDFM_OPTIMIZER_OPTIONS = {
        'Adam': 'Adam (推荐)',
        'SGD': 'SGD'
    }
    DDFM_OPTIMIZER_DEFAULT = 'Adam'

    # 激活函数选项
    DDFM_ACTIVATION_OPTIONS = {
        'relu': 'ReLU (推荐)',
        'tanh': 'Tanh',
        'sigmoid': 'Sigmoid'
    }
    DDFM_ACTIVATION_DEFAULT = 'relu'

    # 因子AR阶数
    DEFAULT_FACTOR_AR_ORDER = 1
    FACTOR_AR_ORDER_MIN = 0
    FACTOR_AR_ORDER_MAX = 5

    # RMSE对齐方式配置
    RMSE_ALIGNMENT_OPTIONS = {
        'current': '当月值 (默认)',
        'next': '下月值'
    }
    DEFAULT_RMSE_ALIGNMENT = 'current'
    RMSE_ALIGNMENT_HELP = "当月值：预测值与当月实际值对比；下月值：预测值与下月实际值对比（适用于数据滞后发布场景）"

    @classmethod
    def get_date_defaults(cls) -> Dict[str, date]:
        """获取日期默认值字典"""
        # 计算验证期结束日期 = 观察期开始日期 - 1周
        validation_end_timestamp = pd.Timestamp(cls.DEFAULT_OBSERVATION_START) - pd.Timedelta(weeks=1)

        return {
            'training_start': cls.DEFAULT_TRAINING_START,
            'validation_start': cls.DEFAULT_VALIDATION_START,
            'validation_end': validation_end_timestamp.date()  # 观察期开始的前一周
        }

    @classmethod
    def get_safe_option_index(cls, options: Dict, value: str, default: str) -> int:
        """
        安全获取选项索引，如果值无效则返回默认值的索引

        Args:
            options: 选项字典
            value: 当前值
            default: 默认值

        Returns:
            有效的索引
        """
        keys = list(options.keys())
        if value in keys:
            return keys.index(value)
        return keys.index(default) if default in keys else 0
