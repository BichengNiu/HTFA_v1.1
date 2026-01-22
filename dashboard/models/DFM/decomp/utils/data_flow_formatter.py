# -*- coding: utf-8 -*-
"""
数据流格式化器

将新闻贡献数据格式化为按日期分组的数据流结构，
用于在UI中展示类似纽约联储的Data Flow表格。
"""

import logging
import pandas as pd
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from collections import defaultdict

from .helpers import normalize_variable_name
from .constants import DEFAULT_INDUSTRY
from ..core.news_impact_calculator import NewsContribution

if TYPE_CHECKING:
    from .industry_aggregator import IndustryAggregator

logger = logging.getLogger(__name__)


class DataFlowFormatter:
    """
    数据流格式化器

    将新闻贡献数据转换为分层结构（日期 > 发布时间 > 变量），
    支持在Streamlit中使用expander展示。
    """

    def __init__(
        self,
        var_industry_map: Optional[Dict[str, str]] = None,
        industry_aggregator: Optional['IndustryAggregator'] = None
    ):
        """
        初始化数据流格式化器

        Args:
            var_industry_map: 变量名到行业的映射字典
            industry_aggregator: 行业聚合器实例(可选,优先使用)
        """
        self.var_industry_map = var_industry_map or {}
        self._industry_aggregator = industry_aggregator

    def _get_industry(self, variable_name: str) -> str:
        """
        获取变量所属行业

        Args:
            variable_name: 变量名

        Returns:
            行业名称
        """
        if self._industry_aggregator:
            return self._industry_aggregator.get_industry(variable_name)
        normalized_name = normalize_variable_name(variable_name)
        return self.var_industry_map.get(normalized_name, DEFAULT_INDUSTRY)

    def format_data_flow(
        self,
        contributions: List[NewsContribution],
        nowcast_series: Optional[pd.Series] = None
    ) -> List[Dict[str, Any]]:
        """
        格式化为数据流结构

        Args:
            contributions: 新闻贡献列表
            nowcast_series: Nowcast时间序列（可选，用于显示累积值）

        Returns:
            数据流列表，格式：
            [
                {
                    'date': '2025-10-24',
                    'nowcast_value': 2.35,
                    'releases': [
                        {
                            'time': '8:35AM',
                            'variable': 'CPI: All items less food and energy',
                            'industry': 'Prices',
                            'actual': 0.23,
                            'impact': 0.01,
                            'is_positive': True
                        },
                        ...
                    ]
                },
                ...
            ]
        """
        if not contributions:
            return []

        # 按日期分组
        date_groups = defaultdict(list)
        for contrib in contributions:
            date_key = contrib.release_date.strftime('%Y-%m-%d')
            date_groups[date_key].append(contrib)

        # 排序日期
        sorted_dates = sorted(date_groups.keys(), reverse=True)  # 最新日期在前

        # 构建数据流
        data_flow = []
        for date_str in sorted_dates:
            contribs_at_date = date_groups[date_str]

            # 获取该日期的Nowcast值（如果有）
            nowcast_value = None
            if nowcast_series is not None:
                try:
                    date_ts = pd.to_datetime(date_str)
                    # 找到最接近的日期
                    if date_ts in nowcast_series.index:
                        nowcast_value = float(nowcast_series.loc[date_ts])
                    else:
                        # 找到不晚于该日期的最后一个值
                        earlier_dates = nowcast_series.index[nowcast_series.index <= date_ts]
                        if len(earlier_dates) > 0:
                            nowcast_value = float(nowcast_series.loc[earlier_dates[-1]])
                except (KeyError, IndexError, TypeError, ValueError) as e:
                    logger.warning(f"无法获取{date_str}的nowcast值: {e}")

            # 格式化发布数据
            releases = []
            for contrib in sorted(contribs_at_date, key=lambda x: x.release_date):
                release = {
                    'time': contrib.release_date.strftime('%H:%M'),
                    'variable': contrib.variable_name,
                    'industry': self._get_industry(contrib.variable_name),
                    'actual': float(contrib.observed_value),
                    'contribution': float(contrib.contribution_pct),
                    'impact': float(contrib.impact_value),
                    'is_positive': contrib.impact_value > 0
                }
                releases.append(release)

            date_entry = {
                'date': date_str,
                'nowcast_value': nowcast_value,
                'releases': releases
            }

            data_flow.append(date_entry)

        return data_flow

    def group_by_date(
        self,
        contributions: List[NewsContribution]
    ) -> Dict[str, List[NewsContribution]]:
        """
        按日期分组贡献数据

        Args:
            contributions: 新闻贡献列表

        Returns:
            日期到贡献列表的映射
        """
        date_groups = defaultdict(list)
        for contrib in contributions:
            date_key = contrib.release_date.strftime('%Y-%m-%d')
            date_groups[date_key].append(contrib)

        return dict(date_groups)

    def get_summary_by_date(
        self,
        contributions: List[NewsContribution]
    ) -> List[Dict[str, Any]]:
        """
        获取按日期的摘要统计

        Args:
            contributions: 新闻贡献列表

        Returns:
            日期摘要列表
        """
        date_groups = self.group_by_date(contributions)

        summaries = []
        for date_str in sorted(date_groups.keys(), reverse=True):
            contribs = date_groups[date_str]

            total_impact = sum(c.impact_value for c in contribs)
            positive_impact = sum(c.impact_value for c in contribs if c.impact_value > 0)
            negative_impact = sum(c.impact_value for c in contribs if c.impact_value < 0)

            summary = {
                'date': date_str,
                'release_count': len(contribs),
                'total_impact': total_impact,
                'positive_impact': positive_impact,
                'negative_impact': negative_impact
            }

            summaries.append(summary)

        return summaries

    def format_for_streamlit_display(
        self,
        contributions: List[NewsContribution],
        nowcast_series: Optional[pd.Series] = None
    ) -> Dict[str, Any]:
        """
        格式化为Streamlit显示友好的数据结构

        Args:
            contributions: 新闻贡献列表
            nowcast_series: Nowcast时间序列

        Returns:
            包含格式化数据的字典
        """
        data_flow = self.format_data_flow(contributions, nowcast_series)
        date_summaries = self.get_summary_by_date(contributions)

        return {
            'data_flow': data_flow,
            'date_summaries': date_summaries,
            'total_dates': len(data_flow),
            'total_releases': len(contributions)
        }
