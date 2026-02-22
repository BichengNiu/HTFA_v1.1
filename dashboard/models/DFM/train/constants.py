# -*- coding: utf-8 -*-
"""
DFM训练模块常量定义

集中管理所有magic number和配置常量
"""

# ==================== DFM模型常量 ====================

# 随机种子
DFM_RANDOM_SEED = 42

# ==================== AR(1)模型默认参数 ====================

# 单因子AR(1)默认系数
DEFAULT_AR1_COEFFICIENT = 0.95

# 单因子Q矩阵默认方差
DEFAULT_Q_VARIANCE = 0.1

# B矩阵默认缩放系数
DEFAULT_B_SCALE = 0.1

# ==================== 数值稳定性常量 ====================

# 正定性检查的最小特征值
MIN_EIGENVALUE_EPSILON = 1e-7

# 零标准差的替代值
ZERO_STD_REPLACEMENT = 1.0

# R矩阵最小方差（用于P矩阵正则化）
R_MATRIX_MIN_VARIANCE = 1e-6

# 新息协方差矩阵正则化因子（用于S_t矩阵）
# 较大的值是因为S_t通常有更大的数值范围
INNOVATION_COVARIANCE_JITTER = 1e-4

# ==================== DDFM模型常量 ====================

# DDFM批量推理的内存保护阈值
DDFM_MAX_BATCH_SIZE = 5000

# ==================== DDFM工具函数常量 (ddfm_utils.py) ====================

# convergence_checker: loss极小时的绝对阈值
CONVERGENCE_ABSOLUTE_THRESHOLD = 1e-8

# convergence_checker: delta裁剪上界
CONVERGENCE_DELTA_MAX = 1000.0

# get_idio: 周度频率判断阈值（中位间隔<=此值视为周度）
WEEKLY_FREQUENCY_GAP_THRESHOLD = 2

# get_idio: std_eps下界（防止数值不稳定）
MIN_STD_EPS = 1e-4

# get_idio: phi裁剪范围（AR系数边界）
AR_COEFFICIENT_CLIP_BOUND = 0.90

# get_idio: 方差分母保护（防止除零）
VARIANCE_DENOMINATOR_JITTER = 1e-8

# ==================== DDFM模型训练常量 (ddfm_model.py) ====================

# _train: 协方差矩阵抖动项
DDFM_COVARIANCE_JITTER = 1e-6

# _build_state_space: eps_var下界
DDFM_EPS_VAR_FLOOR = 0.01

# ==================== DDFM状态转移参数常量 (get_transition_params) ====================

# get_transition_params: 初始协方差放大系数
SIGMA0_SCALE_FACTOR = 2.0

# get_transition_params: 正定性保护
SIGMA0_PD_JITTER = 0.01
