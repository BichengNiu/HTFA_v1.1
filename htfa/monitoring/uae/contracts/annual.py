from __future__ import annotations
from htfa.monitoring.uae.contracts.annual_comparison_contracts import COMPARISON_CHARTS

ANNUAL_CHARTS = (
    *COMPARISON_CHARTS,
    ("年度_资本形成", "资本形成总额（现价）及同比", False),
    ("年度_行业资本形成", "行业资本形成总额及同比（现价，末年前五行业）", True),
    ("年度_外资类型", "外国投资分类（历史数据）", False),
    ("年度_外资行业", "外商直接投资行业分布（历史数据，末年前五行业）", True),
    ("年度_外资来源国", "外商直接投资来源地（历史数据，末年前五项）", True),
)
