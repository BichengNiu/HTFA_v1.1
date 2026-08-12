# -*- coding: utf-8 -*-
"""
日期计算辅助函数

用于DFM模型训练UI中的日期相关计算和验证
支持不同数据频率（日度、周度、旬度、月度）的上一期计算
"""

from datetime import date
from typing import Optional

import pandas as pd


# 频率代码到pandas偏移的映射
FREQUENCY_OFFSETS = {
    'D': pd.Timedelta(days=1),        # 日度
    'W': pd.Timedelta(weeks=1),       # 周度
    '10D': pd.Timedelta(days=10),     # 旬度
    'M': pd.DateOffset(months=1),     # 月度
}

# 频率代码到中文描述的映射
FREQUENCY_LABELS = {
    'D': '日',
    'W': '周',
    '10D': '旬',
    'M': '月',
}

# 频率代码到pandas频率字符串的映射
FREQUENCY_PANDAS = {
    'D': 'D',
    'W': 'W-FRI',  # 周度默认周五
    '10D': '10D',
    'M': 'ME',     # 月末
}

# 所有支持的频率代码（统一来源）
SUPPORTED_FREQ_CODES = frozenset(FREQUENCY_OFFSETS.keys())


def get_previous_period_date(
    reference_date: date,
    freq_code: str,
    periods: int = 1
) -> date:
    """
    根据频率计算上N期的日期

    Args:
        reference_date: 参考日期
        freq_code: 频率代码 ('D', 'W', '10D', 'M')
        periods: 向前偏移的期数，默认1

    Returns:
        上N期的日期

    Raises:
        ValueError: 当freq_code不在支持的频率列表中时
    """
    if freq_code not in SUPPORTED_FREQ_CODES:
        raise ValueError(f"不支持的频率代码: {freq_code}，有效值: {list(SUPPORTED_FREQ_CODES)}")

    offset = FREQUENCY_OFFSETS[freq_code]
    ts = pd.Timestamp(reference_date)

    for _ in range(periods):
        ts = ts - offset

    return ts.date()


def get_frequency_label(freq_code: str) -> str:
    """
    获取频率的中文标签

    Args:
        freq_code: 频率代码

    Returns:
        中文标签（如"周"、"月"）

    Raises:
        ValueError: 当freq_code不在支持的频率列表中时
    """
    if freq_code not in SUPPORTED_FREQ_CODES:
        raise ValueError(f"不支持的频率代码: {freq_code}，有效值: {list(SUPPORTED_FREQ_CODES)}")
    return FREQUENCY_LABELS[freq_code]


def validate_date_ranges(
    algorithm: str,
    training_start: date,
    validation_start: date,
    observation_start: date,
    target_freq: str = 'W'
) -> Optional[str]:
    """
    验证日期范围逻辑

    Args:
        algorithm: 'classical' 或 'deep_learning'
        training_start: 训练期开始日期
        validation_start: 验证期开始日期
        observation_start: 观察期开始日期
        target_freq: 目标变量频率代码

    Returns:
        None 表示验证通过，否则返回错误信息字符串
    """
    freq_label = get_frequency_label(target_freq)

    if algorithm == 'deep_learning':
        # DDFM模式验证
        train_end_limit = get_previous_period_date(observation_start, target_freq, periods=1)
        if training_start >= train_end_limit:
            return (
                f"DDFM模式：训练期开始({training_start})必须早于观察期上一{freq_label}({train_end_limit})"
            )
    else:
        # 经典DFM模式验证
        if training_start >= validation_start:
            return (
                f"经典DFM模式：训练期开始({training_start})必须早于验证期开始({validation_start})"
            )

    return None


def is_ddfm_mode(algorithm: str) -> bool:
    """
    判断是否为DDFM模式

    Args:
        algorithm: 算法类型字符串

    Returns:
        True 如果是深度学习模式，否则 False
    """
    return algorithm == 'deep_learning'


def freq_code_to_pandas_freq(freq_code: str) -> str:
    """
    将内部频率代码转换为pandas频率字符串

    Args:
        freq_code: 内部频率代码 ('D', 'W', '10D', 'M')

    Returns:
        pandas频率字符串

    Raises:
        ValueError: 当freq_code不在支持的频率列表中时
    """
    if freq_code not in FREQUENCY_PANDAS:
        raise ValueError(f"不支持的频率代码: {freq_code}，有效值: {list(SUPPORTED_FREQ_CODES)}")
    return FREQUENCY_PANDAS[freq_code]
