"""数据概览 UI 的纯函数层：选项构建与控件值解析。"""

from .options import (
    build_chart_options,
    build_table_options,
    preview_table_frame,
    series_style_widget_key,
)
from .parsing import (
    detect_frequency,
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
    "build_chart_options",
    "build_table_options",
    "detect_frequency",
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
