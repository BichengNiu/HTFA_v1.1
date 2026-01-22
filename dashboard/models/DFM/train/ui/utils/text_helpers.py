# -*- coding: utf-8 -*-
"""
文本处理工具函数

提供DFM训练UI中常用的文本标准化和处理功能
"""

import unicodedata
from typing import Dict, List


def normalize_variable_name(name: str) -> str:
    """
    标准化变量名（用于映射匹配）

    Args:
        name: 原始变量名

    Returns:
        标准化后的变量名（NFKC标准化 + 去除首尾空格 + 转小写）

    Examples:
        >>> normalize_variable_name("  GDP增速  ")
        'gdp增速'
        >>> normalize_variable_name("全角空格　test")
        '全角空格 test'
    """
    if not name:
        return ""
    return unicodedata.normalize('NFKC', str(name)).strip().lower()


def normalize_variable_name_no_space(name: str) -> str:
    """
    标准化变量名并移除所有空格（用于精确匹配）

    Args:
        name: 原始变量名

    Returns:
        标准化后的变量名（NFKC + 去空格 + 小写）

    Examples:
        >>> normalize_variable_name_no_space("GDP 增速")
        'gdp增速'
    """
    return normalize_variable_name(name).replace(' ', '')


def build_normalized_mapping(
    original_dict: Dict[str, str],
    normalize_key: bool = True,
    normalize_value: bool = False
) -> Dict[str, str]:
    """
    构建标准化后的映射字典

    Args:
        original_dict: 原始映射字典
        normalize_key: 是否标准化键
        normalize_value: 是否标准化值

    Returns:
        标准化后的映射字典

    Examples:
        >>> build_normalized_mapping({"  GDP  ": "经济"}, normalize_key=True)
        {'gdp': '经济'}
    """
    result = {}
    for key, value in original_dict.items():
        if not key or not str(key).strip():
            continue

        new_key = normalize_variable_name(key) if normalize_key else key
        new_value = normalize_variable_name(value) if normalize_value else value

        result[new_key] = new_value

    return result


def filter_exclude_targets(
    all_indicators: List[str],
    exclude_list: List[str]
) -> List[str]:
    """
    从指标列表中排除目标变量

    Args:
        all_indicators: 所有指标列表
        exclude_list: 要排除的变量列表

    Returns:
        排除后的指标列表

    Examples:
        >>> filter_exclude_targets(
        ...     ['GDP', '工业增加值', 'CPI'],
        ...     ['工业增加值']
        ... )
        ['GDP', 'CPI']
    """
    if not exclude_list:
        return all_indicators

    exclude_set = set(exclude_list)
    return [ind for ind in all_indicators if ind not in exclude_set]


def filter_exclude_zonghe(
    indicators: List[str],
    var_industry_map: Dict[str, str]
) -> List[str]:
    """
    从指标列表中排除"综合"类变量

    Args:
        indicators: 指标列表
        var_industry_map: 变量名(标准化) -> 行业名的映射

    Returns:
        排除"综合"变量后的指标列表

    Examples:
        >>> filter_exclude_zonghe(
        ...     ['工业增加值', '综合指标'],
        ...     {'综合指标': '综合'}
        ... )
        ['工业增加值']
    """
    if not var_industry_map:
        return indicators

    return [
        ind for ind in indicators
        if var_industry_map.get(normalize_variable_name(ind), None) != '综合'
    ]


def build_exclude_targets_list(
    current_target_var: str,
    first_stage_targets: List[str] = None
) -> List[str]:
    """
    构建排除目标变量列表

    Args:
        current_target_var: 当前目标变量
        first_stage_targets: 其他需要排除的目标变量列表

    Returns:
        完整的排除目标列表

    Examples:
        >>> build_exclude_targets_list('GDP', ['工业增加值', 'CPI'])
        ['GDP', '工业增加值', 'CPI']
        >>> build_exclude_targets_list(None, ['工业增加值'])
        ['工业增加值']
    """
    exclude_targets = []
    if current_target_var:
        exclude_targets.append(current_target_var)
    if first_stage_targets:
        exclude_targets.extend(first_stage_targets)
    return exclude_targets


def get_valid_indicators_for_industry(
    all_indicators: List[str],
    exclude_targets: List[str],
    var_industry_map: Dict[str, str],
) -> List[str]:
    """
    获取行业的有效预测指标（排除目标变量）

    Args:
        all_indicators: 该行业的所有指标
        exclude_targets: 要排除的目标变量列表
        var_industry_map: 变量名(标准化) -> 行业名的映射

    Returns:
        有效的预测指标列表
    """
    # 排除目标变量
    indicators = filter_exclude_targets(all_indicators, exclude_targets)

    return indicators
