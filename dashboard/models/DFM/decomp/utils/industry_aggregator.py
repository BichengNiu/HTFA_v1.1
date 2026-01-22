# -*- coding: utf-8 -*-
"""
行业分组聚合器

负责按行业分类聚合数据发布影响，为可视化提供分组数据。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from collections import defaultdict

from .helpers import normalize_variable_name
from .constants import DEFAULT_INDUSTRY, INDUSTRY_COLORS
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

    def aggregate_by_industry_and_time(
        self,
        contributions: List[NewsContribution]
    ) -> pd.DataFrame:
        """
        按行业和时间聚合贡献数据

        Args:
            contributions: 新闻贡献列表

        Returns:
            DataFrame，包含每个时间点每个行业的影响值
            索引：时间戳
            列：行业名称
        """
        if not contributions:
            return pd.DataFrame()

        # 创建时间-行业-影响的映射
        time_industry_impact = defaultdict(lambda: defaultdict(float))

        for contrib in contributions:
            industry = self.get_industry(contrib.variable_name)
            timestamp = contrib.release_date
            time_industry_impact[timestamp][industry] += contrib.impact_value

        # 转换为DataFrame
        df = pd.DataFrame.from_dict(time_industry_impact, orient='index')
        df = df.fillna(0)
        df = df.sort_index()

        return df

    def get_industry_ranking(
        self,
        contributions: List[NewsContribution],
        by: str = 'impact',
        top_n: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取行业影响排名

        Args:
            contributions: 新闻贡献列表
            by: 排序依据 ('impact', 'count', 'positive_impact', 'negative_impact')
            top_n: 返回前N个，None表示全部

        Returns:
            排序后的行业列表
        """
        industry_stats = self.aggregate_by_industry(contributions)

        # 转换为列表并排序
        ranking = [
            {
                'industry': industry,
                'impact': stats['impact'],
                'count': stats['count'],
                'positive_impact': stats['positive_impact'],
                'negative_impact': stats['negative_impact'],
                'contribution_pct': stats['contribution_pct']
            }
            for industry, stats in industry_stats.items()
        ]

        # 按指定字段排序（绝对值降序）
        ranking.sort(key=lambda x: abs(x[by]), reverse=True)

        if top_n is not None:
            ranking = ranking[:top_n]

        return ranking

    def prepare_stacked_bar_data(
        self,
        contributions: List[NewsContribution]
    ) -> Dict[str, Any]:
        """
        准备堆叠柱状图数据

        Args:
            contributions: 新闻贡献列表

        Returns:
            堆叠柱状图数据结构：
            {
                'dates': List[str],  # X轴日期
                'industries': List[str],  # 行业列表
                'positive': {  # 正向影响
                    'Production': [0.1, 0.2, ...],
                    'Construction': [0.05, 0.1, ...],
                    ...
                },
                'negative': {  # 负向影响
                    'Production': [-0.1, -0.05, ...],
                    ...
                }
            }
        """
        if not contributions:
            return {'dates': [], 'industries': [], 'positive': {}, 'negative': {}}

        # 按时间分组
        time_groups = defaultdict(list)
        for contrib in contributions:
            time_groups[contrib.release_date].append(contrib)

        # 排序时间
        sorted_dates = sorted(time_groups.keys())

        # 获取所有行业
        all_industries = set()
        for contrib in contributions:
            industry = self.get_industry(contrib.variable_name)
            all_industries.add(industry)

        industries = sorted(list(all_industries))

        # 初始化正负影响字典
        positive_data = {industry: [] for industry in industries}
        negative_data = {industry: [] for industry in industries}

        # 填充每个时间点的数据
        for date in sorted_dates:
            contribs_at_date = time_groups[date]

            # 按行业累加影响
            industry_impact_at_date = defaultdict(lambda: {'pos': 0.0, 'neg': 0.0})

            for contrib in contribs_at_date:
                industry = self.get_industry(contrib.variable_name)
                if contrib.impact_value > 0:
                    industry_impact_at_date[industry]['pos'] += contrib.impact_value
                elif contrib.impact_value < 0:
                    industry_impact_at_date[industry]['neg'] += contrib.impact_value

            # 添加到数据列表
            for industry in industries:
                positive_data[industry].append(industry_impact_at_date[industry]['pos'])
                negative_data[industry].append(industry_impact_at_date[industry]['neg'])

        return {
            'dates': [d.strftime('%Y-%m-%d') for d in sorted_dates],
            'industries': industries,
            'positive': positive_data,
            'negative': negative_data
        }

    def get_industry_color_map(self, industries: List[str]) -> Dict[str, str]:
        """
        获取行业到颜色的映射

        Args:
            industries: 行业列表

        Returns:
            行业颜色映射字典
        """
        # 预定义颜色方案（基于参考图）
        default_colors = {
            'Construction': '#8B4513',    # 棕色
            'Production': '#FF8C00',      # 橙色
            'Surveys': '#1E3A8A',         # 深蓝色
            'Consumption': '#16A34A',     # 绿色
            'Income': '#4ADE80',          # 浅绿色
            'Labor': '#DC2626',           # 红色
            'Trade': '#0EA5E9',           # 蓝色
            'Prices': '#9333EA',          # 紫色
            'Other': '#9CA3AF'            # 灰色
        }

        # 为所有行业分配颜色
        color_map = {}

        for idx, industry in enumerate(industries):
            if industry in default_colors:
                color_map[industry] = default_colors[industry]
            else:
                # 使用可用颜色列表循环分配
                color_idx = idx % len(INDUSTRY_COLORS)
                color_map[industry] = INDUSTRY_COLORS[color_idx]

        return color_map

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

    def get_summary_statistics(
        self,
        contributions: List[NewsContribution]
    ) -> Dict[str, Any]:
        """
        获取行业聚合的摘要统计

        Args:
            contributions: 新闻贡献列表

        Returns:
            摘要统计字典
        """
        industry_stats = self.aggregate_by_industry(contributions)

        summary = {
            'total_industries': len(industry_stats),
            'industries': list(industry_stats.keys()),
            'top_positive_industry': None,
            'top_negative_industry': None,
            'max_positive_impact': 0.0,
            'max_negative_impact': 0.0
        }

        if industry_stats:
            # 找出正向影响最大的行业
            max_positive = max(
                [(ind, stats['positive_impact']) for ind, stats in industry_stats.items()],
                key=lambda x: x[1],
                default=(None, 0)
            )
            summary['top_positive_industry'] = max_positive[0]
            summary['max_positive_impact'] = max_positive[1]

            # 找出负向影响最大的行业
            min_negative = min(
                [(ind, stats['negative_impact']) for ind, stats in industry_stats.items()],
                key=lambda x: x[1],
                default=(None, 0)
            )
            summary['top_negative_industry'] = min_negative[0]
            summary['max_negative_impact'] = min_negative[1]

        return summary
