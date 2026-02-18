# -*- coding: utf-8 -*-
"""
文本处理工具函数

提供DFM训练UI中常用的文本标准化和处理功能
"""

from typing import Dict
from dashboard.models.DFM.utils.text_utils import normalize_variable_name


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
