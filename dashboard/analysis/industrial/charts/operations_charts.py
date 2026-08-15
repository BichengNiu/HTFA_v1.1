"""
Operations Charts
企业经营指标图表
"""

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from dashboard.analysis.industrial.charts.base import (
    BaseChartCreator,
    create_subplot_chart,
)
from dashboard.analysis.industrial.charts.config import (
    OPERATIONS_INDICATORS_CONFIG,
    OPERATIONS_INDICATORS,
)


class OperationsIndicatorsChart(BaseChartCreator):
    """
    企业经营指标图表（四个子图：ROE、利润率、周转率、权益乘数）
    """

    def __init__(self):
        """初始化企业经营指标图表"""
        super().__init__(OPERATIONS_INDICATORS_CONFIG)

    def create(
        self,
        df: pd.DataFrame,
        time_range: str = "3年",
        custom_start_date: Optional[str] = None,
        custom_end_date: Optional[str] = None
    ) -> Optional[go.Figure]:
        """创建2x2子图布局的企业经营指标图表。"""
        return create_subplot_chart(
            self,
            df,
            OPERATIONS_INDICATORS,
            grid_key='2x2',
            rows=2,
            label='企业经营',
            time_range=time_range,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date,
        )
