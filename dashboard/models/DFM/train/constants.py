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
