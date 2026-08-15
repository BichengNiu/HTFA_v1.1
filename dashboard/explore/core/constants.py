"""
常量定义模块

定义explore模块中使用的所有常量，避免魔法数字
"""

# ==================== 数据验证相关常量 ====================

# ADF检验所需的最小样本数
# 原因：ADF检验需要足够的样本来估计自回归模型
MIN_SAMPLES_ADF = 5

# 相关性计算所需的最小样本数
# 原因：至少需要2个点才能计算相关系数
MIN_SAMPLES_CORRELATION = 2

# KL散度计算所需的最小样本数
# 原因：需要足够样本来构建有意义的概率分布
MIN_SAMPLES_KL_DIVERGENCE = 10

# ==================== KL散度相关常量 ====================

# KL散度平滑参数
# 原因：避免log(0)和除零错误
DEFAULT_KL_SMOOTHING_ALPHA = 1e-9

# ==================== 时间序列相关常量 ====================

# 时间间隔容差（天）
TIMEDELTA_TOLERANCE_DAYS = {
    'Daily': (0.8, 1.2),
    'Weekly': (5, 7.9),
    'Ten_Day': (8, 24),
    'Monthly': (25, 35),
    'Quarterly': (85, 100),
    'Annual': (350, 380)
}

# 频率映射：从业务名称到pandas频率代码
FREQUENCY_MAPPINGS = {
    'Daily': 'D',
    'Weekly': 'W-MON',
    'Ten_Day': '10D',
    'Monthly': 'ME',
    'Quarterly': 'QE',
    'Annual': 'YE'
}

# 频率优先级（用于自动选择对齐频率）
FREQUENCY_PRIORITY = {
    'Daily': 1,
    'Weekly': 2,
    'Ten_Day': 2.5,
    'Monthly': 3,
    'Quarterly': 4,
    'Annual': 5
}

# ==================== 文本消息模板 ====================

# ERROR_MESSAGES: 统一的错误消息模板
# 用于所有explore子模块，确保错误消息的一致性（DRY原则）
ERROR_MESSAGES = {
    # 数据验证相关
    'empty_series': '输入序列为空',
    'insufficient_data': '有效数据点不足',
    'not_numeric': '序列非数值类型',
    'no_variance': '序列方差为零',
    'calculation_failed': '计算失败',

    # 序列验证相关
    'target_series_invalid': '目标序列无效',
    'ref_series_invalid': '参考序列无效',
    'candidate_not_found': '候选变量未找到',

    # 分析相关
    'correlation_calc_error': '相关性计算错误',
    'kl_calc_error': 'KL散度计算错误',
    'no_common_data': '对齐后无共同有效数据点',

    # 目标相关
    'no_target_change': '目标无变化',
}

# ==================== 默认参数 ====================

# 领先滞后分析结果显示的最大滞后范围
MAX_DISPLAY_LAG_RANGE = 5

# ==================== 差分处理相关常量 ====================

# 同比差分周期映射（每年包含的观测期数）
SEASONAL_DIFF_MAP = {
    'Monthly': 12,      # 月度：12个月
    'Quarterly': 4,     # 季度：4个季度
    'Weekly': 52,       # 周度：52周
    'Ten_Day': 36,      # 旬度：一年约36旬
    'Annual': 1,        # 年度：退化为环比
    'Daily': None,      # 日度：不支持
    'Irregular': None,
    'Undetermined': None
}

# 频率中文显示映射
FREQUENCY_DISPLAY_NAMES = {
    'Daily': '日度',
    'Weekly': '周度',
    'Ten_Day': '旬度',
    'Monthly': '月度',
    'Quarterly': '季度',
    'Annual': '年度',
    'Irregular': '不规则',
    'Undetermined': '未确定'
}
