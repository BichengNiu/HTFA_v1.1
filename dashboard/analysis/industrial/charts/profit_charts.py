"""
Profit Charts
利润相关图表
"""

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from dashboard.analysis.industrial.charts.base import BaseChartCreator
from dashboard.analysis.industrial.charts.config import (
    PROFIT_CONTRIBUTION_CONFIG,
    STREAM_COLORS
)


class ProfitContributionChart(BaseChartCreator):
    """
    工业企业利润分行业拉动率图表
    堆叠柱状图 + 折线图
    """

    def __init__(self, total_growth: pd.Series):
        """
        初始化利润拉动率图表

        Args:
            total_growth: 总体增速Series
        """
        super().__init__(PROFIT_CONTRIBUTION_CONFIG)
        self.total_growth = total_growth

    def _prepare_data(
        self,
        df: pd.DataFrame,
        time_range: str,
        custom_start_date: Optional[str],
        custom_end_date: Optional[str]
    ) -> pd.DataFrame:
        """准备图表数据"""
        # 过滤拉动率数据
        filtered_contribution = self._filter_by_time_range(
            df, time_range, custom_start_date, custom_end_date
        )

        # 过滤总体增速数据
        total_growth_df = self.total_growth.to_frame('total')
        filtered_total_growth = self._filter_by_time_range(
            total_growth_df, time_range, custom_start_date, custom_end_date
        )

        if filtered_contribution.empty or filtered_total_growth.empty:
            self.logger.warning("过滤后数据为空")
            return pd.DataFrame()

        # 将总体增速添加到数据中（用于后续绘图）
        filtered_contribution['_total_growth'] = filtered_total_growth['total']

        return filtered_contribution

    def _create_traces(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """创建图表traces"""
        # 先添加总体增速折线图
        if '_total_growth' in data.columns:
            y_data_line = data['_total_growth'].dropna()

            if not y_data_line.empty:
                fig.add_trace(go.Scatter(
                    x=y_data_line.index,
                    y=y_data_line,
                    mode='lines+markers',
                    name='利润总额累计同比',
                    line=dict(width=4, color='#1f77b4'),
                    marker=dict(size=7),
                    connectgaps=False,
                    hovertemplate='<b>利润总额累计同比</b><br>' +
                                  '时间: %{x|%Y年%m月}<br>' +
                                  '数值: %{y:.2f}%<extra></extra>'
                ))

        # 获取所有上中下游列并排序
        stream_cols = [col for col in data.columns if col.startswith('上中下游_')]
        stream_cols_sorted = sorted(stream_cols, key=self._stream_sort_key)

        # 添加堆叠柱状图
        for stream_col in stream_cols_sorted:
            y_data = data[stream_col].dropna()

            if not y_data.empty:
                legend_name = stream_col.replace('上中下游_', '')
                color = self._get_color_for_stream(stream_col)

                fig.add_trace(go.Bar(
                    x=y_data.index,
                    y=y_data,
                    name=legend_name,
                    marker_color=color,
                    opacity=0.8,
                    hovertemplate=f'<b>{legend_name}</b><br>' +
                                  '时间: %{x|%Y年%m月}<br>' +
                                  '拉动率: %{y:.2f}百分点<extra></extra>'
                ))

    def _apply_layout(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """应用布局配置"""
        super()._apply_layout(fig, data)

        # 设置为相对堆积模式（正确处理正负值）
        fig.update_layout(barmode='relative')

    @staticmethod
    def _get_color_for_stream(col_name: str) -> str:
        """根据列名返回对应的颜色"""
        for stream_type, color in STREAM_COLORS.items():
            if stream_type in col_name:
                return color
        return '#1f77b4'  # 默认蓝色

    @staticmethod
    def _stream_sort_key(col_name: str) -> tuple:
        """自定义排序：上游优先，然后中游，最后下游"""
        if '上游' in col_name:
            return (0, col_name)
        elif '中游' in col_name:
            return (1, col_name)
        elif '下游' in col_name:
            return (2, col_name)
        else:
            return (3, col_name)
