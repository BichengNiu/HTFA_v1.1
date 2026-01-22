"""
Base Chart Creator
图表创建抽象基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import pandas as pd
import plotly.graph_objects as go
import logging

logger = logging.getLogger(__name__)


@dataclass
class ChartConfig:
    """
    图表配置数据类
    """
    title: str = ""
    height: int = 600
    hovermode: str = 'x unified'
    plot_bgcolor: str = 'white'
    paper_bgcolor: str = 'white'
    show_legend: bool = True
    legend_config: Dict[str, Any] = field(default_factory=lambda: {
        'orientation': 'h',
        'yanchor': 'top',
        'y': -0.18,
        'xanchor': 'center',
        'x': 0.5,
        'font': {'size': 14}
    })
    margin: Dict[str, int] = field(default_factory=lambda: {
        'l': 80, 'r': 50, 't': 50, 'b': 120
    })
    xaxis_config: Dict[str, Any] = field(default_factory=lambda: {
        'title': {'text': '', 'font': {'size': 16}},
        'type': 'date',
        'showgrid': True,
        'gridwidth': 1,
        'gridcolor': 'lightgray',
        'dtick': 'M3',
        'tickformat': '%Y-%m',
        'hoverformat': '%Y-%m',
        'tickfont': {'size': 14}
    })
    yaxis_config: Dict[str, Any] = field(default_factory=lambda: {
        'title': {'text': '%', 'font': {'size': 16}},
        'showgrid': True,
        'gridwidth': 1,
        'gridcolor': 'lightgray',
        'tickfont': {'size': 14}
    })


class BaseChartCreator(ABC):
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

    @abstractmethod
    def _prepare_data(
        self,
        df: pd.DataFrame,
        time_range: str,
        custom_start_date: Optional[str],
        custom_end_date: Optional[str]
    ) -> pd.DataFrame:
        """
        准备图表数据（抽象方法，子类必须实现）

        Args:
            df: 原始数据
            time_range: 时间范围
            custom_start_date: 自定义开始日期
            custom_end_date: 自定义结束日期

        Returns:
            准备好的数据DataFrame
        """
        pass

    @abstractmethod
    def _create_traces(self, fig: go.Figure, data: pd.DataFrame) -> None:
        """
        创建图表traces（抽象方法，子类必须实现）

        Args:
            fig: Plotly Figure对象
            data: 准备好的数据
        """
        pass

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
        from dashboard.analysis.industrial.utils import filter_data_by_time_range
        return filter_data_by_time_range(df, time_range, custom_start_date, custom_end_date)
