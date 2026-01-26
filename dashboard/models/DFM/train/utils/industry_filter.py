# -*- coding: utf-8 -*-
"""
行业过滤工具
提供行业和指标过滤功能
"""

from typing import List, Dict


def filter_industries_with_indicators(
    industries: List[str],
    industry_to_vars: Dict[str, List[str]]
) -> List[str]:
    """
    过滤掉没有指标的行业

    Args:
        industries: 行业名称列表
        industry_to_vars: 行业到变量列表的映射

    Returns:
        过滤后的行业列表（至少包含一个变量）
    """
    filtered = []
    for industry in industries:
        vars_in_industry = industry_to_vars.get(industry, [])
        if vars_in_industry:
            filtered.append(industry)

    return filtered
