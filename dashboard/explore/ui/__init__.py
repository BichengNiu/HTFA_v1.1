"""数据探索 Streamlit 页面与组件。

组件由路由或注册表按具体模块加载，包初始化不主动导入全部页面。
"""

from importlib import import_module

_LAZY_EXPORTS = {
    "TimeSeriesAnalysisComponent": (
        "dashboard.explore.ui.base",
        "TimeSeriesAnalysisComponent",
    ),
    "StationarityAnalysisComponent": (
        "dashboard.explore.ui.stationarity",
        "StationarityAnalysisComponent",
    ),
    "StructuralBreakAnalysisComponent": (
        "dashboard.explore.ui.structural_break",
        "StructuralBreakAnalysisComponent",
    ),
    "CorrelationAnalysisComponent": (
        "dashboard.explore.ui.correlation",
        "CorrelationAnalysisComponent",
    ),
    "DTWAnalysisComponent": (
        "dashboard.explore.ui.dtw",
        "DTWAnalysisComponent",
    ),
    "LeadLagAnalysisComponent": (
        "dashboard.explore.ui.lead_lag",
        "LeadLagAnalysisComponent",
    ),
    "UnifiedCorrelationAnalysisComponent": (
        "dashboard.explore.ui.unified_correlation",
        "UnifiedCorrelationAnalysisComponent",
    ),
    "DataExplorationWelcomePage": (
        "dashboard.explore.ui.pages",
        "DataExplorationWelcomePage",
    ),
    "render_univariate_analysis_page": (
        "dashboard.explore.ui.univariate_page",
        "render_univariate_analysis_page",
    ),
    "render_bivariate_analysis_page": (
        "dashboard.explore.ui.bivariate_page",
        "render_bivariate_analysis_page",
    ),
}

__all__ = tuple(_LAZY_EXPORTS)


def __getattr__(name: str):
    """按需解析原有 UI 包导出。"""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc

    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
