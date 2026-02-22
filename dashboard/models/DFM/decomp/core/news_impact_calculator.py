# -*- coding: utf-8 -*-
"""
新闻影响计算器

专门处理新闻项的边际贡献分析，包括贡献度排名、
正负影响分解和关键驱动变量识别。
"""

import pandas as pd
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass

from ..utils.exceptions import ComputationError, ValidationError, decomp_error_handler
from .impact_analyzer import DataRelease

logger = logging.getLogger(__name__)


@dataclass
class NewsContribution:
    """新闻贡献项"""
    variable_name: str
    impact_value: float
    contribution_pct: float
    is_positive: bool
    release_date: pd.Timestamp
    observed_value: float
    expected_value: float
    kalman_weight: float
    confidence_interval: Optional[Tuple[float, float]] = None  # 与ImpactResult保持一致


class NewsImpactCalculator:
    """
    新闻影响计算器

    专门分析数据发布对nowcast的边际贡献，提供详细的贡献度分析
    和变量排名功能。
    """

    def __init__(self, impact_analyzer):
        """
        初始化新闻影响计算器

        Args:
            impact_analyzer: 影响分析器实例
        """
        self.analyzer = impact_analyzer

    def calculate_news_contributions(
        self,
        releases: List[DataRelease],
        target_date: pd.Timestamp
    ) -> List[NewsContribution]:
        """
        计算各数据发布的贡献

        Args:
            releases: 数据发布列表
            target_date: 目标日期

        Returns:
            新闻贡献列表

        Raises:
            ComputationError: 计算失败时抛出
        """
        with decomp_error_handler("新闻贡献计算"):
            # 获取时序影响结果
            sequential_result = self.analyzer.analyze_sequential_impacts(releases, target_date)

            # 转换为新闻贡献格式
            contributions = []
            total_abs_impact = sum(abs(imp.impact_on_target) for imp in sequential_result.individual_impacts)

            for impact_result in sequential_result.individual_impacts:
                release = impact_result.release

                # 计算贡献百分比
                contribution_pct = (
                    abs(impact_result.impact_on_target) / total_abs_impact * 100
                    if total_abs_impact > 0 else 0
                )

                contribution = NewsContribution(
                    variable_name=release.variable_name,
                    impact_value=impact_result.impact_on_target,
                    contribution_pct=contribution_pct,
                    is_positive=impact_result.impact_on_target > 0,
                    release_date=release.timestamp,
                    observed_value=release.observed_value,
                    expected_value=release.expected_value,
                    kalman_weight=impact_result.kalman_weight,
                    confidence_interval=impact_result.confidence_interval
                )

                contributions.append(contribution)

            logger.info(f"计算了 {len(contributions)} 个新闻贡献")
            return contributions

    def rank_variables_by_impact(
        self,
        contributions: List[NewsContribution]
    ) -> pd.DataFrame:
        """
        按总影响绝对值对变量进行排名

        Args:
            contributions: 新闻贡献列表

        Returns:
            排名数据框

        Raises:
            ComputationError: 排名失败时抛出
        """
        with decomp_error_handler("变量排名"):
            # 按变量分组
            variable_data = {}
            for contrib in contributions:
                var_name = contrib.variable_name
                if var_name not in variable_data:
                    variable_data[var_name] = []
                variable_data[var_name].append(contrib)

            # 计算每个变量的统计指标
            ranking_data = []
            for var_name, var_contributions in variable_data.items():
                total_impact = sum(c.impact_value for c in var_contributions)
                avg_impact = total_impact / len(var_contributions) if var_contributions else 0
                total_contribution_pct = sum(c.contribution_pct for c in var_contributions)
                positive_count = sum(1 for c in var_contributions if c.is_positive)
                negative_count = len(var_contributions) - positive_count

                ranking_data.append({
                    'variable_name': var_name,
                    'total_impact': total_impact,
                    'avg_impact': avg_impact,
                    'total_contribution_pct': total_contribution_pct,
                    'release_count': len(var_contributions),
                    'positive_count': positive_count,
                    'negative_count': negative_count,
                })

            # 创建数据框
            ranking_df = pd.DataFrame(ranking_data)

            # 如果没有数据，返回空DataFrame（带列名）
            if len(ranking_df) == 0:
                logger.warning("contributions为空，返回空排名DataFrame")
                return pd.DataFrame(columns=[
                    'rank', 'variable_name', 'total_impact', 'avg_impact',
                    'total_contribution_pct', 'release_count', 'positive_count',
                    'negative_count',
                ])

            # 按总影响绝对值排名
            ranking_df = ranking_df.sort_values('total_impact', key=abs, ascending=False)
            ranking_df['rank'] = range(1, len(ranking_df) + 1)

            logger.info("变量排名完成")
            return ranking_df

