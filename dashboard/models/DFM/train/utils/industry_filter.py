# -*- coding: utf-8 -*-
"""
行业过滤工具
提供行业和指标过滤功能
"""

from typing import List, Dict


def filter_industries_by_target(
    industries: List[str],
    industry_to_vars: Dict[str, List[str]],
    target_var: str
) -> List[str]:
    """
    过滤掉仅包含目标变量的行业

    Args:
        industries: 行业名称列表
        industry_to_vars: 行业到变量列表的映射
        target_var: 目标变量名称

    Returns:
        过滤后的行业列表（至少包含一个非目标变量）
    """
    if not target_var:
        return industries

    filtered = []
    for industry in industries:
        vars_in_industry = industry_to_vars.get(industry, [])
        non_target_vars = [v for v in vars_in_industry if v != target_var]
        if non_target_vars:
            filtered.append(industry)

    return filtered


def get_non_target_indicators(
    indicators: List[str],
    target_var: str
) -> List[str]:
    """
    从指标列表中排除目标变量

    Args:
        indicators: 指标列表
        target_var: 目标变量名称

    Returns:
        排除目标变量后的指标列表
    """
    if not target_var:
        return indicators

    return [ind for ind in indicators if ind != target_var]
