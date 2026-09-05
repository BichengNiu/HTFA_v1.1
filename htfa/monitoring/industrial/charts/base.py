"""
Base Chart Creator
图表创建抽象基类
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging

from htfa.monitoring.industrial.utils.chart_config import (
    CHART_HEIGHT_STANDARD,
    LEGEND_CONFIG_BOTTOM_CENTER,
    create_xaxis_config,
    create_yaxis_config,
)

logger = logging.getLogger(__name__)


@dataclass
class ChartConfig:
    """
    图表配置数据类

    布局默认值统一取自 utils/chart_config.py，避免双轨配置漂移。
    """
    title: str = ""
    height: int = CHART_HEIGHT_STANDARD
    hovermode: str = 'x unified'
    plot_bgcolor: str = 'white'
    paper_bgcolor: str = 'white'
    show_legend: bool = True
    barmode: str | None = None
    legend_config: Dict[str, Any] = field(
        default_factory=lambda: dict(LEGEND_CONFIG_BOTTOM_CENTER)
    )
    margin: Dict[str, int] = field(default_factory=lambda: {
        'l': 80, 'r': 50, 't': 50, 'b': 120
    })
    xaxis_config: Dict[str, Any] = field(
        default_factory=lambda: create_xaxis_config()
    )
    yaxis_config: Dict[str, Any] = field(
        default_factory=lambda: create_yaxis_config(title='%')
    )


class BaseChartCreator:
    """
    图表创建器抽象基类

    使用模板方法模式，定义图表创建的标准流程：
    1. 准备数据（_prepare_data）
    2. 创建traces（_create_traces）
    3. 应用布局配置（_apply_layout）
    """

    def __init__(self, config: Optional[ChartConfig] = None):
        """
        初始化图表创建器

        Args:
            config: 图表配置，如果未提供则使用默认配置
        """
        self.config = config or ChartConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

    def _prepare_data(
        self,
        df: pd.DataFrame,
        time_range: str,
        custom_start_date: Optional[str],
        custom_end_date: Optional[str]
    ) -> pd.DataFrame:
        """
        准备图表数据（模板方法钩子；使用模板 create() 的子类应覆写）

        Args:
            df: 原始数据
            time_range: 时间范围
            custom_start_date: 自定义开始日期
            custom_end_date: 自定义结束日期

        Returns:
            准备好的数据DataFrame
        """
        return df

    def _create_traces(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """
        创建图表traces（模板方法钩子；使用模板 create() 的子类应覆写）

        Args:
            fig: Plotly Figure对象
            data: 准备好的数据
        """
        raise NotImplementedError(
            "使用模板 create() 的子类必须实现 _create_traces"
        )

    def create(
        self,
        df: pd.DataFrame,
        time_range: str = "3年",
        custom_start_date: Optional[str] = None,
        custom_end_date: Optional[str] = None
    ) -> Optional[go.Figure]:
        """
        创建图表（模板方法）

        Args:
            df: 原始数据
            time_range: 时间范围选择
            custom_start_date: 自定义开始日期
            custom_end_date: 自定义结束日期

        Returns:
            Plotly Figure对象，失败时返回None
        """
        try:
            # 步骤1: 准备数据
            prepared_data = self._prepare_data(df, time_range, custom_start_date, custom_end_date)

            if prepared_data is None or prepared_data.empty:
                self.logger.warning("准备数据后为空")
                return None

            # 步骤2: 创建Figure对象
            fig = go.Figure()

            # 步骤3: 创建traces
            self._create_traces(fig, prepared_data)

            # 步骤4: 应用布局配置
            self._apply_layout(fig, prepared_data)

            return fig

        except Exception as e:
            self.logger.error(f"创建图表时发生错误: {e}", exc_info=True)
            return None

    def _apply_layout(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """
        应用统一的布局配置

        Args:
            fig: Plotly Figure对象
            data: 准备好的数据
        """
        # 计算数据时间范围
        min_date = data.index.min() if not data.empty else None
        max_date = data.index.max() if not data.empty else None

        # 复制x轴配置并设置范围
        xaxis_config = dict(self.config.xaxis_config)
        if min_date and max_date:
            xaxis_config['range'] = [min_date, max_date]

        # 应用布局
        layout_config = {
            'title': {'text': self.config.title, 'font': {'size': 18}},
            'xaxis': xaxis_config,
            'yaxis': self.config.yaxis_config,
            'hovermode': self.config.hovermode,
            'height': self.config.height,
            'margin': self.config.margin,
            'showlegend': self.config.show_legend,
            'plot_bgcolor': self.config.plot_bgcolor,
            'paper_bgcolor': self.config.paper_bgcolor
        }

        if self.config.show_legend:
            layout_config['legend'] = self.config.legend_config
        if self.config.barmode:
            layout_config['barmode'] = self.config.barmode

        fig.update_layout(**layout_config)

    def _filter_by_time_range(
        self,
        df: pd.DataFrame,
        time_range: str,
        custom_start_date: Optional[str],
        custom_end_date: Optional[str]
    ) -> pd.DataFrame:
        """
        按时间范围过滤数据（公共工具方法）

        Args:
            df: 输入数据
            time_range: 时间范围
            custom_start_date: 自定义开始日期
            custom_end_date: 自定义结束日期

        Returns:
            过滤后的数据
        """
        from htfa.monitoring.industrial.utils import filter_data_by_time_range
        return filter_data_by_time_range(df, time_range, custom_start_date, custom_end_date)


# 子图间距配置（仅 create_subplot_chart 使用，保持在本模块避免与 config 循环依赖）
SUBPLOT_SPACING = {
    '2x2': {'vertical_spacing': 0.12, 'horizontal_spacing': 0.1},
    '3x2': {'vertical_spacing': 0.12, 'horizontal_spacing': 0.1}
}

# 子图边距配置
SUBPLOT_MARGINS = {
    '2x2': {'top': 80, 'bottom': 60, 'left': 60, 'right': 60},
    '3x2': {'top': 80, 'bottom': 60, 'left': 60, 'right': 60}
}


def create_subplot_chart(
    chart_creator: "BaseChartCreator",
    df: pd.DataFrame,
    indicators: list,
    *,
    grid_key: str,
    rows: int,
    label: str,
    time_range: str = "3年",
    custom_start_date: Optional[str] = None,
    custom_end_date: Optional[str] = None,
) -> Optional[go.Figure]:
    """按 rows×2 网格绘制指标子图（企业经营指标/效率指标共用）。

    与原先 OperationsIndicatorsChart / EfficiencyMetricsChart 的 create()
    行为一致，仅提取了共同的子图构建逻辑。
    """
    try:
        # 准备数据
        filtered_df = chart_creator._filter_by_time_range(
            df, time_range, custom_start_date, custom_end_date
        )

        if filtered_df.empty:
            chart_creator.logger.warning("过滤后数据为空")
            return None

        available_indicators = [
            ind for ind in indicators if ind['name'] in filtered_df.columns
        ]

        if not available_indicators:
            chart_creator.logger.warning(f"未找到任何{label}指标")
            return None

        # 创建 rows x 2 子图布局
        spacing = SUBPLOT_SPACING[grid_key]
        fig = make_subplots(
            rows=rows, cols=2,
            subplot_titles=[ind['title'] for ind in indicators],
            vertical_spacing=spacing['vertical_spacing'],
            horizontal_spacing=spacing['horizontal_spacing'],
            specs=[[{"secondary_y": False}, {"secondary_y": False}]] * rows
        )

        # 为每个子图添加数据
        for idx, indicator in enumerate(indicators):
            row = idx // 2 + 1
            col = idx % 2 + 1

            if indicator['name'] in filtered_df.columns:
                y_data = filtered_df[indicator['name']].dropna()

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
        margins = SUBPLOT_MARGINS[grid_key]
        fig.update_layout(
            height=chart_creator.config.height,
            hovermode=chart_creator.config.hovermode,
            showlegend=False,
            margin=dict(l=margins['left'], r=margins['right'],
                       t=margins['top'], b=margins['bottom']),
            plot_bgcolor=chart_creator.config.plot_bgcolor,
            paper_bgcolor=chart_creator.config.paper_bgcolor,
            title=dict(
                text=chart_creator.config.title,
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
        chart_creator.logger.error(f"创建{label}指标图表时发生错误: {e}", exc_info=True)
        return None
