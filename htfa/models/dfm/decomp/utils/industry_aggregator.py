# -*- coding: utf-8 -*-
"""
行业分组聚合器

负责按行业分类聚合数据发布影响，为可视化提供分组数据。
"""

from typing import Dict, List, Any, Optional
from collections import defaultdict

from htfa.models.dfm.utils.text_utils import normalize_variable_name
from .constants import DEFAULT_INDUSTRY
from ..core.news_impact_calculator import NewsContribution


class IndustryAggregator:
    """
    行业分组聚合器

    将新闻贡献数据按行业分类进行聚合统计，支持
    纽约联储风格的分类堆叠图表数据准备。
    """

    def __init__(self, var_industry_map: Optional[Dict[str, str]] = None):
        """
        初始化行业聚合器

        Args:
            var_industry_map: 变量名到行业的映射字典
        """
        self.var_industry_map = var_industry_map or {}
        self.default_industry = DEFAULT_INDUSTRY

    def aggregate_by_industry(
        self,
        contributions: List[NewsContribution]
    ) -> Dict[str, Dict[str, Any]]:
        """
        按行业聚合贡献数据

        Args:
            contributions: 新闻贡献列表

        Returns:
            行业聚合统计字典，格式：
            {
                'Production': {
                    'impact': 0.5,
                    'count': 10,
                    'positive_impact': 0.8,
                    'negative_impact': -0.3,
                    'contribution_pct': 25.0
                },
                ...
            }
        """
        if not contributions:
            return {}

        # 初始化行业统计
        industry_stats = defaultdict(lambda: {
            'impact': 0.0,
            'count': 0,
            'positive_impact': 0.0,
            'negative_impact': 0.0,
            'contribution_pct': 0.0
        })

        # 修正：使用绝对值之和作为分母，避免正负抵消导致百分比爆炸
        total_abs_impact = sum(abs(c.impact_value) for c in contributions)

        # 按行业累加统计
        for contrib in contributions:
            industry = self.get_industry(contrib.variable_name)

            industry_stats[industry]['impact'] += contrib.impact_value
            industry_stats[industry]['count'] += 1

            if contrib.impact_value > 0:
                industry_stats[industry]['positive_impact'] += contrib.impact_value
            elif contrib.impact_value < 0:
                industry_stats[industry]['negative_impact'] += contrib.impact_value

        # 计算贡献百分比（使用绝对值进行归一化）
        for industry in industry_stats:
            impact = industry_stats[industry]['impact']
            industry_stats[industry]['contribution_pct'] = (
                (abs(impact) / total_abs_impact * 100) if total_abs_impact > 0 else 0
            )

        return dict(industry_stats)

    def get_industry(self, variable_name: str) -> str:
        """
        获取变量所属行业（公共方法）

        Args:
            variable_name: 变量名

        Returns:
            行业名称
        """
        normalized_name = normalize_variable_name(variable_name)
        return self.var_industry_map.get(normalized_name, self.default_industry)
