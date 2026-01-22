# -*- coding: utf-8 -*-
"""
数据探索UI组件包
包含所有时间序列分析相关的UI组件
"""

from dashboard.explore.ui.base import TimeSeriesAnalysisComponent
from dashboard.explore.ui.stationarity import StationarityAnalysisComponent
from dashboard.explore.ui.correlation import CorrelationAnalysisComponent
from dashboard.explore.ui.dtw import DTWAnalysisComponent
from dashboard.explore.ui.lead_lag import LeadLagAnalysisComponent
from dashboard.explore.ui.unified_correlation import UnifiedCorrelationAnalysisComponent
from dashboard.explore.ui.pages import DataExplorationWelcomePage
from dashboard.explore.ui.univariate_page import render_univariate_analysis_page
from dashboard.explore.ui.bivariate_page import render_bivariate_analysis_page

__all__ = [
    'TimeSeriesAnalysisComponent',
    'StationarityAnalysisComponent',
    'CorrelationAnalysisComponent',
    'DTWAnalysisComponent',
    'LeadLagAnalysisComponent',
    'UnifiedCorrelationAnalysisComponent',
    'DataExplorationWelcomePage',
    'render_univariate_analysis_page',
    'render_bivariate_analysis_page',
]
