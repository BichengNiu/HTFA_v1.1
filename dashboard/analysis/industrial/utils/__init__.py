"""
Industrial Analysis Utils Module
工业分析工具模块 - 提供共享的工具函数

This module contains shared utility functions to eliminate code duplication:
- time_filter: 时间范围过滤
- weight_calculator: 权重计算
- data_converter: 数据转换
- data_loader: 数据加载（带缓存）
- chart_config: 图表配置常量和函数
- chart_creator_unified: 统一的图表创建器（消除180行重复）
- fragment_components: 统一的Fragment组件（消除240行重复）
- download_utils: 统一的Excel下载工具（消除90行重复）
"""

from dashboard.analysis.industrial.utils.time_filter import filter_data_by_time_range
from dashboard.analysis.industrial.utils.weight_calculator import get_weight_for_year, filter_data_from_2012
from dashboard.analysis.industrial.utils.data_converter import convert_cumulative_to_yoy, convert_margin_to_yoy_diff, convert_cumulative_to_current
from dashboard.analysis.industrial.utils.data_loader import (
    load_macro_data,
    load_weights_data,
    load_overall_industrial_data,
    load_profit_breakdown_data,
    load_enterprise_profit_data,
    load_industry_profit_data,
    load_enterprise_operations_data
)
from dashboard.analysis.industrial.utils.chart_config import (
    # 常量
    TIME_RANGE_OPTIONS,
    DEFAULT_TIME_RANGE,
    DEFAULT_TIME_RANGE_INDEX,
    CHART_COLORS,
    CHART_HEIGHT_STANDARD,
    CHART_HEIGHT_COMPACT,
    CHART_MARGIN_STANDARD,
    CHART_MARGIN_WITH_LEGEND,
    LEGEND_CONFIG_BOTTOM_CENTER,
    LEGEND_CONFIG_BOTTOM_CENTER_LARGE,
    XAXIS_CONFIG_BASE,
    YAXIS_CONFIG_BASE,
    DTICK_3_MONTHS,
    DTICK_6_MONTHS,
    DTICK_12_MONTHS,
    # 函数
    get_chart_color,
    get_time_range_index,
    create_xaxis_config,
    create_yaxis_config,
    create_standard_layout,
    get_opacity_by_index,
    calculate_dtick_by_time_span
)
from dashboard.analysis.industrial.utils.chart_creator_unified import (
    create_time_series_chart,
    create_mixed_chart,
    clean_variable_name,
    get_date_range_from_data,
    create_line_trace
)
from dashboard.analysis.industrial.utils.fragment_components import (
    render_time_range_selector,
    create_chart_with_time_selector_fragment,
    render_chart_group_with_download,
    render_multiple_charts_with_separators
)
from dashboard.analysis.industrial.utils.download_utils import (
    create_excel_file,
    create_excel_download_button,
    create_download_with_annotation,
    create_grouping_mappings,
    prepare_grouping_annotation_data
)
# 加权计算模块（优化版本）
from dashboard.analysis.industrial.utils.weighted_calculation import calculate_weighted_groups_optimized
# 统一状态管理
from dashboard.analysis.industrial.utils.state_manager import IndustrialStateManager

__all__ = [
    # 数据处理
    'filter_data_by_time_range',
    'get_weight_for_year',
    'filter_data_from_2012',
    'convert_cumulative_to_yoy',
    'convert_margin_to_yoy_diff',
    'convert_cumulative_to_current',
    # 数据加载
    'load_macro_data',
    'load_weights_data',
    'load_overall_industrial_data',
    'load_profit_breakdown_data',
    'load_enterprise_profit_data',
    'load_industry_profit_data',
    'load_enterprise_operations_data',
    # 图表配置常量
    'TIME_RANGE_OPTIONS',
    'DEFAULT_TIME_RANGE',
    'DEFAULT_TIME_RANGE_INDEX',
    'CHART_COLORS',
    'CHART_HEIGHT_STANDARD',
    'CHART_HEIGHT_COMPACT',
    'CHART_MARGIN_STANDARD',
    'CHART_MARGIN_WITH_LEGEND',
    'LEGEND_CONFIG_BOTTOM_CENTER',
    'LEGEND_CONFIG_BOTTOM_CENTER_LARGE',
    'XAXIS_CONFIG_BASE',
    'YAXIS_CONFIG_BASE',
    'DTICK_3_MONTHS',
    'DTICK_6_MONTHS',
    'DTICK_12_MONTHS',
    # 图表配置函数
    'get_chart_color',
    'get_time_range_index',
    'create_xaxis_config',
    'create_yaxis_config',
    'create_standard_layout',
    'get_opacity_by_index',
    'calculate_dtick_by_time_span',
    # 统一图表创建器
    'create_time_series_chart',
    'create_mixed_chart',
    'clean_variable_name',
    'get_date_range_from_data',
    'create_line_trace',
    # 统一Fragment组件
    'render_time_range_selector',
    'create_chart_with_time_selector_fragment',
    'render_chart_group_with_download',
    'render_multiple_charts_with_separators',
    # 统一Excel下载工具
    'create_excel_file',
    'create_excel_download_button',
    'create_download_with_annotation',
    'create_grouping_mappings',
    'prepare_grouping_annotation_data',
    # 优化的加权计算
    'calculate_weighted_groups_optimized',
    # 统一状态管理
    'IndustrialStateManager',
]
