"""
图表组件模块
提供各种类型的图表组件，基于Plotly实现
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, Any, Optional, List
import streamlit as st
from datetime import datetime
import logging
import warnings
from dashboard.analysis.industrial.ui.shared.base import BaseAnalysisComponent

warnings.filterwarnings("ignore", category = DeprecationWarning)

logger = logging.getLogger(__name__)


class ChartComponent(BaseAnalysisComponent):
    """
    基础图表组件类
    提供通用的图表创建和配置功能
    """

    def __init__(self, state_manager):
        """初始化图表组件"""
        super().__init__(state_manager)

        self.chart_config = {
            'title': '',
            'width': 800,
            'height': 500,
            'theme': 'plotly_white'
        }

        self.default_layout = {
            'hovermode': 'closest',
            'hoverlabel': {
                'bgcolor': "white",
                'font_size': 12,
            },
            'legend': {
                'orientation': "h",
                'yanchor': "bottom",
                'y': -0.2,
                'xanchor': "center",
                'x': 0.5
            },
            'margin': {'l': 50, 'r': 30, 't': 60, 'b': 100}
        }

    def set_chart_config(self, config: Dict[str, Any]):
        """
        设置图表配置

        Args:
            config: 图表配置字典
        """
        self.chart_config.update(config)
        logger.debug(f"更新图表配置: {config}")

    def create_base_figure(self) -> go.Figure:
        """
        创建基础图表对象

        Returns:
            Plotly图表对象
        """
        fig = go.Figure()

        self.apply_default_layout(fig)

        if self.chart_config.get('title'):
            fig.update_layout(title=self.chart_config['title'])

        return fig

    def apply_default_layout(self, fig: go.Figure):
        """
        应用默认布局到图表

        Args:
            fig: Plotly图表对象
        """
        fig.update_layout(**self.default_layout)

        if self.chart_config.get('width') and self.chart_config.get('height'):
            fig.update_layout(
                width=self.chart_config['width'],
                height=self.chart_config['height']
            )

    def render_chart(self, fig: go.Figure, key: str = None):
        """
        在Streamlit中渲染图表

        Args:
            fig: Plotly图表对象
            key: Streamlit组件的唯一键
        """
        try:
            st.plotly_chart(
                fig,
                width='stretch',
                key=key
            )
        except Exception as e:
            self.handle_error(e, "图表渲染")

    def render(self):
        """基础渲染方法 - 子类需要重写"""
        st.info("请使用具体的图表组件类")


class TimeSeriesChartComponent(ChartComponent):
    """
    时间序列图表组件
    用于显示时间序列数据的图表
    """

    def create_time_series_chart(
        self,
        data: pd.Series,
        title: str = "",
        show_trend: bool = False,
        show_moving_average: bool = False,
        ma_window: int = 7
    ) -> go.Figure:
        """
        创建时间序列图表

        Args:
            data: 时间序列数据
            title: 图表标题
            show_trend: 是否显示趋势线
            show_moving_average: 是否显示移动平均线
            ma_window: 移动平均窗口大小

        Returns:
            Plotly图表对象
        """
        try:
            self.set_chart_config({'title': title})

            fig = self.create_base_figure()

            fig.add_trace(go.Scatter(
                x=data.index,
                y=data.values,
                mode='lines+markers',
                name=data.name or '数据',
                line=dict(color='blue', width=2),
                hovertemplate='%{x}<br>%{y:.2f}<extra></extra>'
            ))

            if show_trend:
                self.add_trend_line(fig, data)

            if show_moving_average:
                self.add_moving_average(fig, data, ma_window)

            fig.update_layout(
                xaxis_title="时间",
                yaxis_title="数值"
            )

            return fig

        except Exception as e:
            self.handle_error(e, "创建时间序列图表")
            return self.create_base_figure()

    def add_trend_line(self, fig: go.Figure, data: pd.Series):
        """
        添加趋势线

        Args:
            fig: Plotly图表对象
            data: 时间序列数据
        """
        try:
            x_numeric = np.arange(len(data))
            z = np.polyfit(x_numeric, data.values, 1)
            trend_line = np.poly1d(z)(x_numeric)

            fig.add_trace(go.Scatter(
                x=data.index,
                y=trend_line,
                mode='lines',
                name='趋势线',
                line=dict(color='red', dash='dash', width=2),
                hovertemplate='趋势线: %{y:.2f}<extra></extra>'
            ))

        except Exception as e:
            logger.error(f"添加趋势线失败: {e}")

    def add_moving_average(self, fig: go.Figure, data: pd.Series, window: int):
        """
        添加移动平均线

        Args:
            fig: Plotly图表对象
            data: 时间序列数据
            window: 移动平均窗口大小
        """
        try:
            ma_data = data.rolling(window=window).mean()

            fig.add_trace(go.Scatter(
                x=ma_data.index,
                y=ma_data.values,
                mode='lines',
                name=f'{window}日移动平均',
                line=dict(color='green', dash='dot', width=2),
                hovertemplate=f'{window}日移动平均: %{{y:.2f}}<extra></extra>'
            ))

        except Exception as e:
            logger.error(f"添加移动平均线失败: {e}")

    def render(self):
        """渲染时间序列图表组件"""
        st.subheader("时间序列图表")

        data = self.get_data_from_state('time_series_data')

        if self.validate_data(data):
            fig = self.create_time_series_chart(
                data=data,
                title="时间序列分析",
                show_trend=True,
                show_moving_average=True
            )

            self.render_chart(fig, key="time_series_chart")
        else:
            st.warning("没有可用的时间序列数据")


class WeeklyChartComponent(ChartComponent):
    """
    周度图表组件
    用于显示周度数据分析图表
    """

    def create_weekly_chart(
        self,
        indicator_series: pd.Series,
        historical_stats: pd.DataFrame,
        indicator_name: str,
        current_year: int,
        previous_year: int
    ) -> go.Figure:
        """
        创建周度分析图表

        Args:
            indicator_series: 指标时间序列
            historical_stats: 历史统计数据
            indicator_name: 指标名称
            current_year: 当前年份
            previous_year: 上一年份

        Returns:
            Plotly图表对象
        """
        try:
            self.set_chart_config({'title': indicator_name})

            fig = self.create_base_figure()

            indicator_series.index = pd.to_datetime(indicator_series.index)

            current_year_data = indicator_series[indicator_series.index.year == current_year].copy()
            previous_year_data = indicator_series[indicator_series.index.year == previous_year].copy()

            all_weeks = pd.Index(range(1, 54), name='week')
            week_indices = all_weeks.values

            plot_data = pd.DataFrame(index=all_weeks)
            plot_data = plot_data.join(historical_stats)

            if not current_year_data.empty:
                current_year_plot_data = current_year_data.groupby(
                    current_year_data.index.isocalendar().week
                ).last().reindex(all_weeks)
                plot_data[f'{current_year}年'] = current_year_plot_data

            if not previous_year_data.empty:
                previous_year_plot_data = previous_year_data.groupby(
                    previous_year_data.index.isocalendar().week
                ).last().reindex(all_weeks)
                plot_data[f'{previous_year}年'] = previous_year_plot_data

            self.add_historical_range(fig, historical_stats)

            self.add_historical_mean(fig, plot_data, week_indices)

            if f'{previous_year}年' in plot_data.columns:
                self.add_year_data(fig, plot_data, week_indices, previous_year, 'blue')

            if f'{current_year}年' in plot_data.columns:
                self.add_year_data(fig, plot_data, week_indices, current_year, 'red')

            fig.update_layout(
                xaxis_title="周数",
                yaxis_title="数值",
                xaxis=dict(
                    tickmode='linear',
                    tick0=1,
                    dtick=4
                )
            )

            return fig

        except Exception as e:
            self.handle_error(e, "创建周度图表")
            return self.create_base_figure()

    def add_historical_range(self, fig: go.Figure, historical_stats: pd.DataFrame):
        """添加历史区间"""
        try:
            valid_hist_mask = ~(historical_stats['hist_max'].isna() | historical_stats['hist_min'].isna())

            if valid_hist_mask.any():
                valid_weeks = historical_stats.index.values[valid_hist_mask]
                valid_hist_max = historical_stats['hist_max'].values[valid_hist_mask]
                valid_hist_min = historical_stats['hist_min'].values[valid_hist_mask]

                fig.add_trace(go.Scatter(
                    x=np.concatenate([valid_weeks, valid_weeks[::-1]]),
                    y=np.concatenate([valid_hist_max, valid_hist_min[::-1]]),
                    fill='toself',
                    fillcolor='rgba(211, 211, 211, 0.5)',
                    line=dict(color='rgba(255,255,255,0)'),
                    hoverinfo='skip',
                    showlegend=True,
                    name='历史区间'
                ))
        except Exception as e:
            logger.error(f"添加历史区间失败: {e}")

    def add_historical_mean(self, fig: go.Figure, plot_data: pd.DataFrame, week_indices: np.ndarray):
        """添加历史均值线"""
        try:
            fig.add_trace(go.Scatter(
                x=week_indices,
                y=plot_data['hist_mean'],
                mode='lines+markers',
                line=dict(color='grey', dash='dash'),
                name='近3年均值',
                showlegend=True,
                hovertemplate='近3年均值 (W%{x}): %{y:.2f}<extra></extra>'
            ))
        except Exception as e:
            logger.error(f"添加历史均值线失败: {e}")

    def add_year_data(self, fig: go.Figure, plot_data: pd.DataFrame, week_indices: np.ndarray, year: int, color: str):
        """添加年度数据线"""
        try:
            fig.add_trace(go.Scatter(
                x=week_indices,
                y=plot_data[f'{year}年'],
                mode='lines+markers',
                name=f'{year}年',
                line=dict(color=color),
                hovertemplate=f'{year}年 (W%{{x}}): %{{y:.2f}}<extra></extra>'
            ))
        except Exception as e:
            logger.error(f"添加{year}年数据失败: {e}")

    def render(self):
        """渲染周度图表组件"""
        st.subheader("周度数据分析")

        indicator_data = self.get_data_from_state('weekly_indicator_data')
        historical_stats = self.get_data_from_state('weekly_historical_stats')

        if self.validate_data(indicator_data) and self.validate_data(historical_stats):
            fig = self.create_weekly_chart(
                indicator_series=indicator_data,
                historical_stats=historical_stats,
                indicator_name="周度指标分析",
                current_year=2024,
                previous_year=2023
            )

            self.render_chart(fig, key="weekly_chart")
        else:
            st.warning("没有可用的周度数据")
