"""
Enterprise Indicators Chart
企业指标图表（混合线图和条形图）
"""

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from dashboard.analysis.industrial.charts.base import BaseChartCreator
from dashboard.analysis.industrial.charts.config import (
    ENTERPRISE_INDICATORS_CONFIG,
    COLOR_PALETTE
)
from dashboard.analysis.industrial.constants import (
    PROFIT_TOTAL_COLUMN,
    CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
    PPI_COLUMN,
    PROFIT_MARGIN_COLUMN_YOY,
    CHART_COLORS,
    ENTERPRISE_INDICATOR_LEGEND_MAPPING,
    BAR_CHART_INDICATORS,
    LINE_CHART_INDICATORS
)


class EnterpriseIndicatorsChart(BaseChartCreator):
    """
    企业指标图表
    混合条形图（堆叠）和折线图
    """

    def __init__(self):
        """初始化企业指标图表"""
        super().__init__(ENTERPRISE_INDICATORS_CONFIG)

    def _prepare_data(
        self,
        df: pd.DataFrame,
        time_range: str,
        custom_start_date: Optional[str],
        custom_end_date: Optional[str]
    ) -> pd.DataFrame:
        """准备图表数据"""
        # 应用时间过滤
        filtered_df = self._filter_by_time_range(
            df, time_range, custom_start_date, custom_end_date
        )

        # 定义需要的四个指标
        required_indicators = [
            PROFIT_TOTAL_COLUMN,
            CUMULATIVE_INDUSTRIAL_GROWTH_COLUMN,
            PPI_COLUMN,
            PROFIT_MARGIN_COLUMN_YOY
        ]

        # 检查哪些指标存在于数据中
        available_indicators = [ind for ind in required_indicators if ind in df.columns]

        if not available_indicators:
            self.logger.warning("没有可用指标")
            return pd.DataFrame()

        # 处理数据 - 只保留可用指标
        complete_data_df = filtered_df[available_indicators].copy()

        # 转换所有列为数值型
        for col in complete_data_df.columns:
            complete_data_df[col] = pd.to_numeric(complete_data_df[col], errors='coerce')

        # 保留至少有1个指标数据的行
        non_null_counts = complete_data_df.count(axis=1)
        valid_rows = non_null_counts >= 1
        complete_data_df = complete_data_df[valid_rows]

        if complete_data_df.empty:
            self.logger.warning("过滤后数据为空")
            return pd.DataFrame()

        return complete_data_df

    def _create_traces(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """创建图表traces"""
        colors = CHART_COLORS

        # 先添加线图指标
        for i, column in enumerate(data.columns):
            y_data = data[column].dropna()

            if y_data.empty:
                continue

            # 检查是否应该用线图
            is_line_indicator = any(line_key in column for line_key in LINE_CHART_INDICATORS)

            if is_line_indicator:
                legend_name = ENTERPRISE_INDICATOR_LEGEND_MAPPING.get(column, column)
                fig.add_trace(go.Scatter(
                    x=y_data.index,
                    y=y_data,
                    mode='lines+markers',
                    name=legend_name,
                    line=dict(width=4, color=colors[i % len(colors)]),
                    marker=dict(size=7),
                    connectgaps=False,
                    hovertemplate=f'<b>{legend_name}</b><br>' +
                                  '时间: %{x|%Y年%m月}<br>' +
                                  '数值: %{y:.2f}%<extra></extra>'
                ))

        # 添加条形图指标
        for i, column in enumerate(data.columns):
            y_data = data[column].dropna()

            if y_data.empty:
                continue

            # 检查是否应该用条形图
            is_bar_indicator = any(bar_key in column for bar_key in BAR_CHART_INDICATORS)

            if is_bar_indicator:
                legend_name = ENTERPRISE_INDICATOR_LEGEND_MAPPING.get(column, column)

                # 计算渐变透明度
                opacity_value = 0.9 - (i * 0.15)
                opacity_value = max(0.5, opacity_value)

                fig.add_trace(go.Bar(
                    x=y_data.index,
                    y=y_data,
                    name=legend_name,
                    marker_color=colors[i % len(colors)],
                    opacity=opacity_value,
                    hovertemplate=f'<b>{legend_name}</b><br>' +
                                  '时间: %{x|%Y年%m月}<br>' +
                                  '数值: %{y:.2f}%<extra></extra>'
                ))

    def _apply_layout(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """应用布局配置"""
        super()._apply_layout(fig, data)

        # 设置为相对堆积模式（正确处理正负值）
        fig.update_layout(barmode='relative')
