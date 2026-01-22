"""
Efficiency Charts
企业经营效率指标图表
"""

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dashboard.analysis.industrial.charts.base import BaseChartCreator
from dashboard.analysis.industrial.charts.config import (
    EFFICIENCY_METRICS_CONFIG,
    EFFICIENCY_INDICATORS,
    SUBPLOT_SPACING,
    SUBPLOT_MARGINS
)


class EfficiencyMetricsChart(BaseChartCreator):
    """
    企业经营效率指标图表（六个子图：成本、费用、资产收入、人均收入、产成品周转天数、应收账款平均回收期）
    """

    def __init__(self):
        """初始化企业经营效率指标图表"""
        super().__init__(EFFICIENCY_METRICS_CONFIG)

    def _prepare_data(
        self,
        df: pd.DataFrame,
        time_range: str,
        custom_start_date: Optional[str],
        custom_end_date: Optional[str]
    ) -> pd.DataFrame:
        """准备图表数据"""
        filtered_df = self._filter_by_time_range(
            df, time_range, custom_start_date, custom_end_date
        )

        if filtered_df.empty:
            self.logger.warning("过滤后数据为空")
            return pd.DataFrame()

        # 检查哪些指标存在于数据中
        available_indicators = [
            ind for ind in EFFICIENCY_INDICATORS
            if ind['name'] in filtered_df.columns
        ]

        if not available_indicators:
            self.logger.warning("未找到任何企业经营效率指标")
            return pd.DataFrame()

        return filtered_df

    def _create_traces(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """创建图表traces"""
        # 注意：这个方法不会被调用，因为我们重写了create方法
        pass

    def create(
        self,
        df: pd.DataFrame,
        time_range: str = "3年",
        custom_start_date: Optional[str] = None,
        custom_end_date: Optional[str] = None
    ) -> Optional[go.Figure]:
        """
        创建图表（重写以支持子图布局）

        Args:
            df: 原始数据
            time_range: 时间范围选择
            custom_start_date: 自定义开始日期
            custom_end_date: 自定义结束日期

        Returns:
            Plotly Figure对象
        """
        try:
            # 准备数据
            prepared_data = self._prepare_data(df, time_range, custom_start_date, custom_end_date)

            if prepared_data is None or prepared_data.empty:
                return None

            # 创建3x2子图布局
            spacing = SUBPLOT_SPACING['3x2']
            fig = make_subplots(
                rows=3, cols=2,
                subplot_titles=[ind['title'] for ind in EFFICIENCY_INDICATORS],
                vertical_spacing=spacing['vertical_spacing'],
                horizontal_spacing=spacing['horizontal_spacing'],
                specs=[[{"secondary_y": False}, {"secondary_y": False}],
                       [{"secondary_y": False}, {"secondary_y": False}],
                       [{"secondary_y": False}, {"secondary_y": False}]]
            )

            # 为每个子图添加数据
            for idx, indicator in enumerate(EFFICIENCY_INDICATORS):
                row = idx // 2 + 1
                col = idx % 2 + 1

                if indicator['name'] in prepared_data.columns:
                    y_data = prepared_data[indicator['name']].dropna()

                    if not y_data.empty:
                        fig.add_trace(
                            go.Scatter(
                                x=y_data.index,
                                y=y_data,
                                mode='lines+markers',
                                name=indicator['title'],
                                line=dict(width=3, color=indicator['color']),
                                marker=dict(size=7),
                                showlegend=False,
                                connectgaps=False,
                                hovertemplate=(
                                    f'<b>{indicator["title"]}</b><br>' +
                                    '时间: %{x|%Y年%m月}<br>' +
                                    f'数值: %{{y:.2f}}{indicator["suffix"]}<extra></extra>'
                                )
                            ),
                            row=row, col=col
                        )

                        # 更新y轴范围（添加10%边距）
                        y_min = y_data.min()
                        y_max = y_data.max()
                        y_range = y_max - y_min
                        margin = y_range * 0.1 if y_range > 0 else 0.1

                        fig.update_yaxes(
                            title_text=indicator['yaxis_title'],
                            showgrid=True,
                            gridwidth=1,
                            gridcolor='rgba(128, 128, 128, 0.2)',
                            tickfont=dict(size=11),
                            title_font=dict(size=12),
                            range=[y_min - margin, y_max + margin],
                            row=row, col=col
                        )

            # 更新所有x轴
            fig.update_xaxes(
                title_text='',
                showgrid=True,
                gridwidth=1,
                gridcolor='rgba(128, 128, 128, 0.2)',
                dtick="M3",
                tickformat='%Y-%m',
                tickfont=dict(size=11)
            )

            # 更新整体布局
            margins = SUBPLOT_MARGINS['3x2']
            fig.update_layout(
                height=self.config.height,
                hovermode=self.config.hovermode,
                showlegend=False,
                margin=dict(l=margins['left'], r=margins['right'],
                           t=margins['top'], b=margins['bottom']),
                plot_bgcolor=self.config.plot_bgcolor,
                paper_bgcolor=self.config.paper_bgcolor,
                title=dict(
                    text=self.config.title,
                    x=0,
                    xanchor='left',
                    font=dict(size=18)
                )
            )

            # 更新子图标题样式
            for annotation in fig['layout']['annotations']:
                annotation['font'] = dict(size=14, color='#333')

            return fig

        except Exception as e:
            self.logger.error(f"创建企业经营效率指标图表时发生错误: {e}", exc_info=True)
            return None
