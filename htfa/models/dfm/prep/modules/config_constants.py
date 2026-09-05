"""
配置和常量模块

包含数据准备过程中使用的所有配置参数和常量定义
"""

# 数据质量阈值
MIN_VALID_DATE_RATIO = 0.5       # 日期解析最低有效比例
MIN_PREDICTOR_VALID_RATIO = 0.3 # 预测变量最低有效比例

# 频率优先级顺序（数字越小频率越高）
FREQ_ORDER = {
    'D': 1,      # 日度
    'K': 1.5,    # 旬度
    'W': 2,      # 周度
    '10D': 2.5,  # 旬度
    'M': 3,      # 月度
    'Q': 4,      # 季度
    'Y': 5       # 年度
}

# 频率周期映射（天数）- 用于统计计算
FREQ_DAYS_MAP = {
    '日度': 1, '日': 1, 'daily': 1, 'd': 1,
    '周度': 7, '周': 7, 'weekly': 7, 'w': 7,
    '旬度': 10, '旬': 10, 'dekad': 10,
    '月度': 30, '月': 30, 'monthly': 30, 'm': 30,
    '季度': 90, '季': 90, 'quarterly': 90, 'q': 90,
    '年度': 365, '年': 365, 'yearly': 365, 'annual': 365, 'y': 365
}

# 导出的常量
__all__ = [
    'MIN_VALID_DATE_RATIO',
    'MIN_PREDICTOR_VALID_RATIO',
    'FREQ_ORDER',
    'FREQ_DAYS_MAP'
]
