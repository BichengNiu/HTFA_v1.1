# -*- coding: utf-8 -*-
"""
Preview模块频率处理工具
提供通用的频率迭代、筛选、判断等功能
消除硬编码，提供统一的频率访问接口
"""

from typing import Dict, List, Set, Optional, Iterator, Any
import pandas as pd

from dashboard.preview.modules.industrial.config import (
    UNIFIED_FREQUENCY_CONFIGS,
    FREQUENCY_ORDER,
    CHINESE_TO_ENGLISH_FREQ,
    ENGLISH_TO_CHINESE_FREQ
)


def get_indicator_frequencies(indicator: str, all_data_dict: Dict[str, pd.DataFrame]) -> List[str]:
    """获取指标存在的所有频率

    Args:
        indicator: 指标名称
        all_data_dict: {频率名: DataFrame}字典

    Returns:
        list: 频率名称列表（按FREQUENCY_ORDER排序）

    Examples:
        >>> freqs = get_indicator_frequencies('指标A', all_data_dict)
        >>> print(freqs)  # ['周度', '月度']
    """
    frequencies = []

    for freq_name in FREQUENCY_ORDER:
        df = all_data_dict.get(freq_name)
        if df is not None and not df.empty and indicator in df.columns:
            frequencies.append(freq_name)

    return frequencies


def filter_indicators_by_frequency(
    all_indicators: Set[str],
    all_data_dict: Dict[str, pd.DataFrame],
    target_frequencies: Optional[List[str]] = None
) -> Dict[str, List[str]]:
    """按频率筛选指标

    Args:
        all_indicators: 所有指标集合
        all_data_dict: {频率名: DataFrame}字典
        target_frequencies: 目标频率列表，None表示所有频率

    Returns:
        dict: {频率名: [指标列表]}

    Examples:
        >>> result = filter_indicators_by_frequency(
        ...     all_indicators, all_data_dict, ['周度', '月度']
        ... )
        >>> # {'周度': ['指标A', '指标B'], '月度': ['指标A', '指标C']}
    """
    result = {}

    for freq_name, df in all_data_dict.items():
        # 如果指定了目标频率，则跳过不匹配的
        if target_frequencies and freq_name not in target_frequencies:
            continue

        if df is not None and not df.empty:
            indicators = [ind for ind in all_indicators if ind in df.columns]
            if indicators:
                result[freq_name] = indicators

    return result


def iter_all_frequencies(use_english: bool = True) -> Iterator[str]:
    """迭代所有频率

    Args:
        use_english: True返回英文名，False返回中文名

    Yields:
        频率名称

    Examples:
        >>> list(iter_all_frequencies(True))
        ['weekly', 'monthly', 'daily', 'ten_day', 'yearly']
        >>> list(iter_all_frequencies(False))
        ['周度', '月度', '日度', '旬度', '年度']
    """
    if use_english:
        for freq_name in UNIFIED_FREQUENCY_CONFIGS.keys():
            yield freq_name
    else:
        for freq_name in UNIFIED_FREQUENCY_CONFIGS.keys():
            yield UNIFIED_FREQUENCY_CONFIGS[freq_name]['display_name']


def create_empty_frequency_dict(default_value: Any = None, use_english: bool = True) -> Dict[str, Any]:
    """创建空的频率字典（避免硬编码）

    Args:
        default_value: 默认值（可以是None, [], set(), pd.DataFrame()等）
        use_english: True使用英文键，False使用中文键

    Returns:
        频率字典

    Examples:
        >>> create_empty_frequency_dict(set())
        {'weekly': set(), 'monthly': set(), ...}
        >>> create_empty_frequency_dict(pd.DataFrame(), use_english=False)
        {'周度': DataFrame(...), '月度': DataFrame(...), ...}
    """
    result = {}

    if use_english:
        for freq_name in UNIFIED_FREQUENCY_CONFIGS.keys():
            # 为可变类型创建独立实例
            if isinstance(default_value, (list, set, dict)):
                result[freq_name] = type(default_value)()
            elif isinstance(default_value, pd.DataFrame):
                result[freq_name] = pd.DataFrame()
            else:
                result[freq_name] = default_value
    else:
        for freq_name in UNIFIED_FREQUENCY_CONFIGS.keys():
            display_name = UNIFIED_FREQUENCY_CONFIGS[freq_name]['display_name']
            if isinstance(default_value, (list, set, dict)):
                result[display_name] = type(default_value)()
            elif isinstance(default_value, pd.DataFrame):
                result[display_name] = pd.DataFrame()
            else:
                result[display_name] = default_value

    return result


def get_all_frequency_names(use_english: bool = True) -> List[str]:
    """获取所有频率名称列表

    Args:
        use_english: True返回英文名，False返回中文名

    Returns:
        频率名称列表

    Examples:
        >>> get_all_frequency_names(True)
        ['weekly', 'monthly', 'daily', 'ten_day', 'yearly']
        >>> get_all_frequency_names(False)
        ['周度', '月度', '日度', '旬度', '年度']
    """
    return list(iter_all_frequencies(use_english))
