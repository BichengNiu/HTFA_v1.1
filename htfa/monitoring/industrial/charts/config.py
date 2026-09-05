"""
Chart Configuration
图表配置常量
"""

from htfa.monitoring.industrial.charts.base import ChartConfig
from htfa.monitoring.industrial.utils.chart_config import CHART_COLORS

# 颜色调色板（单一数据源：utils/chart_config.CHART_COLORS）
_PALETTE_KEYS = [
    'blue', 'orange', 'green', 'red', 'purple',
    'brown', 'pink', 'gray', 'olive', 'cyan',
]
COLOR_PALETTE = dict(zip(_PALETTE_KEYS, CHART_COLORS))

# 上中下游颜色映射
STREAM_COLORS = {
    '上游': COLOR_PALETTE['red'],
    '中游': COLOR_PALETTE['orange'],
    '下游': COLOR_PALETTE['green']
}

# 利润拉动率图表配置
PROFIT_CONTRIBUTION_CONFIG = ChartConfig(
    title="工业企业利润结构:分上中下游行业",
    height=600,
    hovermode='x unified',
    plot_bgcolor='white',
    paper_bgcolor='white',
    show_legend=True,
    barmode='relative',
    legend_config={
        'orientation': 'h',
        'yanchor': 'top',
        'y': -0.18,
        'xanchor': 'center',
        'x': 0.5,
        'font': {'size': 14}
    }
)

# 企业经营指标图表配置（2x2子图）
OPERATIONS_INDICATORS_CONFIG = ChartConfig(
    title="净资产收益率分析",
    height=700,
    hovermode='x unified',
    plot_bgcolor='white',
    paper_bgcolor='white',
    show_legend=False
)

# 企业经营效率指标图表配置（3x2子图）
EFFICIENCY_METRICS_CONFIG = ChartConfig(
    title="企业经营效率指标",
    height=1000,
    hovermode='x unified',
    plot_bgcolor='white',
    paper_bgcolor='white',
    show_legend=False
)

# 企业指标图表配置
ENTERPRISE_INDICATORS_CONFIG = ChartConfig(
    title="工业企业利润拆解",
    height=600,
    hovermode='x unified',
    plot_bgcolor='white',
    paper_bgcolor='white',
    show_legend=True,
    barmode='relative'
)

# 企业经营指标定义
OPERATIONS_INDICATORS = [
    {'name': 'ROE', 'title': 'ROE', 'color': COLOR_PALETTE['blue'], 'suffix': '%', 'yaxis_title': '%'},
    {'name': '利润率', 'title': '利润率', 'color': COLOR_PALETTE['orange'], 'suffix': '%', 'yaxis_title': '%'},
    {'name': '总资产周转率', 'title': '总资产周转率', 'color': COLOR_PALETTE['green'], 'suffix': '次', 'yaxis_title': '次数'},
    {'name': '权益乘数', 'title': '权益乘数', 'color': COLOR_PALETTE['red'], 'suffix': '倍', 'yaxis_title': '倍数'}
]

# 企业经营效率指标定义
EFFICIENCY_INDICATORS = [
    {'name': '每百元营业收入中的成本', 'title': '每百元营业收入中的成本:累计同比', 'color': COLOR_PALETTE['blue'], 'suffix': '%', 'yaxis_title': '%'},
    {'name': '每百元营业收入中的费用', 'title': '每百元营业收入中的费用:累计同比', 'color': COLOR_PALETTE['orange'], 'suffix': '%', 'yaxis_title': '%'},
    {'name': '每百元资产实现的营业收入', 'title': '每百元资产实现的营业收入:累计同比', 'color': COLOR_PALETTE['green'], 'suffix': '%', 'yaxis_title': '%'},
    {'name': '人均营业收入', 'title': '人均营业收入:累计同比', 'color': COLOR_PALETTE['red'], 'suffix': '%', 'yaxis_title': '%'},
    {'name': '产成品周转天数', 'title': '产成品周转天数:累计同比', 'color': COLOR_PALETTE['purple'], 'suffix': '%', 'yaxis_title': '%'},
    {'name': '应收账款平均回收期', 'title': '应收账款平均回收期:累计同比', 'color': COLOR_PALETTE['brown'], 'suffix': '%', 'yaxis_title': '%'}
]
