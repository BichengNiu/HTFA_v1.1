# -*- coding: utf-8 -*-
"""
DFM Decomp模块常量定义

集中管理所有数值常量，避免魔法数字散落在代码中。
"""

# 置信区间计算
CONFIDENCE_INTERVAL_Z_SCORE = 1.96  # 95%置信区间Z值
DEFAULT_MEASUREMENT_ERROR = 0.1     # 默认测量误差

# 归一化阈值
NORMALIZATION_ZERO_THRESHOLD = 1e-10  # 归一化时判断是否接近零的阈值

# 可视化颜色方案
WATERFALL_COLORS = {
    'positive': '#2E8B57',    # 海绿色 - 正向影响
    'negative': '#DC143C',    # 深红色 - 负向影响
    'neutral': '#708090',     # 石板灰 - 中性
    'baseline': '#4169E1',    # 皇家蓝 - 基准线
    'total': '#FFD700'        # 金色 - 总计
}

# 默认行业分类
DEFAULT_INDUSTRY = "Other"
