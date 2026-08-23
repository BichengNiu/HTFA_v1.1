"""数据概览纯逻辑层：常量、解析与选项构建。"""

from .dataset import (
    OverviewDataset,
    build_overview_dataset,
    numeric_variable_names,
)
from .options import (
    build_chart_options,
    build_table_options,
    preview_table_frame,
    series_style_widget_key,
)
from .parsing import (
    detect_frequency,
    parse_color_sequence,
    parse_csv_items,
    parse_float,
    parse_hlines,
    parse_key_value_mapping,
    parse_shade,
    parse_vlines,
    period_bounds,
    resolve_position,
    time_mask,
)

__all__ = [
    "OverviewDataset",
    "build_chart_options",
    "build_overview_dataset",
    "build_table_options",
    "detect_frequency",
    "numeric_variable_names",
    "parse_color_sequence",
    "parse_csv_items",
    "parse_float",
    "parse_hlines",
    "parse_key_value_mapping",
    "parse_shade",
    "parse_vlines",
    "period_bounds",
    "preview_table_frame",
    "resolve_position",
    "series_style_widget_key",
    "time_mask",
]
