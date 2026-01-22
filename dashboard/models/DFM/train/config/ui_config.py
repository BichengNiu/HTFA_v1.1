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

    # 目标值选项
    TARGET_ALIGNMENT_OPTIONS = {
        'next_month': "下月值",
        'current_month': "本月值"
    }
    DEFAULT_TARGET_ALIGNMENT = 'next_month'

    # 因子选择策略
    FACTOR_STRATEGIES = {
        'fixed_number': "固定因子数 (默认)",
        'cumulative_variance': "累积方差贡献",
        'kaiser': "Kaiser准则 (特征值>1)"
    }
    DEFAULT_FACTOR_STRATEGY = 'fixed_number'

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

    # 变量选择方法
    VARIABLE_SELECTION_METHODS = {
        'none': "无筛选 (使用全部已选变量)",
        'backward': "后向选择法 (逐步移除不重要变量)",
        'stepwise': "向前向后法 (逐步添加并检查冗余变量)"
    }
    DEFAULT_VAR_SELECTION = 'none'

    # 变量选择保留数配置 (2026-01新增)
    MIN_VARIABLES_AFTER_SELECTION_DEFAULT = 5  # 默认最少保留变量数
    MIN_VARIABLES_AFTER_SELECTION_MIN = 3
    MIN_VARIABLES_AFTER_SELECTION_MAX = 20

    # 筛选策略选项
    SELECTION_CRITERIA = {
        'rmse': "RMSE",
        'win_rate': "胜率",
        'hybrid': "混合"
    }
    DEFAULT_SELECTION_CRITERION = 'hybrid'

    # 混合策略优先级选项
    HYBRID_PRIORITIES = {
        'win_rate_first': "胜率优先",
        'rmse_first': "RMSE优先"
    }
    DEFAULT_HYBRID_PRIORITY = 'win_rate_first'

    # 训练期权重配置 (2025-12新增)
    DEFAULT_TRAINING_WEIGHT = 50  # 默认50%训练期权重（百分比）
    TRAINING_WEIGHT_MIN = 0       # 0%=仅验证期
    TRAINING_WEIGHT_MAX = 100     # 100%=仅训练期
    TRAINING_WEIGHT_STEP = 10

    # 容忍度配置 (2026-01新增)
    DEFAULT_RMSE_TOLERANCE = 1.0  # RMSE容忍度（百分比）
    RMSE_TOLERANCE_MIN = 0.5
    RMSE_TOLERANCE_MAX = 5.0
    RMSE_TOLERANCE_STEP = 0.1

    DEFAULT_WIN_RATE_TOLERANCE = 5.0  # Win Rate容忍度（百分比）
    WIN_RATE_TOLERANCE_MIN = 1.0
    WIN_RATE_TOLERANCE_MAX = 10.0
    WIN_RATE_TOLERANCE_STEP = 0.5

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

    # 输入滞后期配置
    LAGS_INPUT_MIN = 0
    LAGS_INPUT_MAX = 5
    LAGS_INPUT_DEFAULT = 0
    LAGS_INPUT_HELP = "包含多少期滞后变量作为输入（0=仅当期）"

    # 批量归一化配置
    BATCH_NORM_DEFAULT = True
    BATCH_NORM_HELP = "批量归一化可提高训练稳定性"

    # EM算法配置
    EM_MAX_ITERATIONS_DEFAULT = 30  # 默认最大迭代次数
    EM_MAX_ITERATIONS_MIN = 10
    EM_MAX_ITERATIONS_MAX = 100
    EM_MAX_ITERATIONS_STEP = 5
    EM_TOLERANCE = 1e-6

    # 因子AR阶数
    DEFAULT_FACTOR_AR_ORDER = 1
    FACTOR_AR_ORDER_MIN = 0
    FACTOR_AR_ORDER_MAX = 5

    # UI布局配置
    NUM_COLS_INDUSTRY = 3
    MAX_ITERATIONS_STEP = 10

    # 文件上传配置
    EXCEL_MAPPING_SHEET = '指标字典'
    INDICATOR_COLUMN_NAME = '指标名称'
    INDUSTRY_COLUMN_NAME = '行业'
    TYPE_COLUMN_NAME = '类型'

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
