"""
工业分析共享UI组件
"""

from dashboard.analysis.industrial.ui.shared.base import BaseAnalysisComponent
from dashboard.analysis.industrial.ui.shared.charts import (
    ChartComponent,
    TimeSeriesChartComponent,
    WeeklyChartComponent
)
from dashboard.analysis.industrial.ui.shared.tables import (
    TableComponent,
    SummaryTableComponent,
    DataTableComponent
)

__all__ = [
    'BaseAnalysisComponent',
    'ChartComponent',
    'TimeSeriesChartComponent',
    'WeeklyChartComponent',
    'TableComponent',
    'SummaryTableComponent',
    'DataTableComponent'
]
