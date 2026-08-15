"""
Efficiency Charts
企业经营效率指标图表
"""

from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from dashboard.analysis.industrial.charts.base import (
    BaseChartCreator,
    create_subplot_chart,
)
from dashboard.analysis.industrial.charts.config import (
    EFFICIENCY_METRICS_CONFIG,
    EFFICIENCY_INDICATORS,
)


class EfficiencyMetricsChart(BaseChartCreator):
    """
    企业经营效率指标图表（六个子图：成本、费用、资产收入、人均收入、产成品周转天数、应收账款平均回收期）
    """

    def __init__(self):
        """初始化企业经营效率指标图表"""
        super().__init__(EFFICIENCY_METRICS_CONFIG)

    def create(
        self,
        df: pd.DataFrame,
        time_range: str = "3年",
        custom_start_date: Optional[str] = None,
        custom_end_date: Optional[str] = None
    ) -> Optional[go.Figure]:
        """创建3x2子图布局的企业经营效率指标图表。"""
        return create_subplot_chart(
            self,
            df,
            EFFICIENCY_INDICATORS,
            grid_key='3x2',
            rows=3,
            label='企业经营效率',
            time_range=time_range,
            custom_start_date=custom_start_date,
            custom_end_date=custom_end_date,
        )
