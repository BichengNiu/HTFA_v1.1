"""
Industrial Analysis Utils Module
工业分析工具模块 - 提供共享的工具函数

此模块通过 re-export 提供一个精简的公共 API。
仅供外部消费者直接使用，内部实现细节不在此导出。
"""

from htfa.monitoring.industrial.utils.time_filter import filter_data_by_time_range
from htfa.monitoring.industrial.utils.weight_calculator import get_weight_for_year, filter_data_from_2012
from htfa.monitoring.industrial.utils.data_converter import convert_cumulative_to_yoy, convert_margin_to_yoy_diff, convert_cumulative_to_current
from htfa.monitoring.industrial.utils.data_loader import (
    load_macro_data,
    load_weights_data,
    load_overall_industrial_data,
    load_enterprise_profit_data,
    load_industry_profit_data,
    load_enterprise_operations_data,
)
from htfa.monitoring.industrial.utils.chart_creator_unified import create_time_series_chart
from htfa.monitoring.industrial.utils.fragment_components import create_chart_with_time_selector_fragment
from htfa.monitoring.industrial.utils.download_utils import (
    create_excel_download_button,
    create_download_with_annotation,
    create_grouping_mappings,
    prepare_grouping_annotation_data,
)

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
    'load_enterprise_profit_data',
    'load_industry_profit_data',
    'load_enterprise_operations_data',
    # 统一图表创建器
    'create_time_series_chart',
    # 统一Fragment组件
    'create_chart_with_time_selector_fragment',
    # 统一Excel下载工具
    'create_excel_download_button',
    'create_download_with_annotation',
    'create_grouping_mappings',
    'prepare_grouping_annotation_data',
]
