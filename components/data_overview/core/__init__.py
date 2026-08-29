"""数据概览纯逻辑层：常量、解析与选项构建。"""

from .dataset import (
    OverviewDataset,
    build_overview_dataset,
    numeric_variable_names,
)
from .file_parsing import (
    FileParseError,
    build_dataframe_from_rows,
    file_fingerprint,
    list_excel_sheets,
    load_dataframe,
    read_raw_rows,
)
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
    "OverviewDataset",
    "FileParseError",
    "build_chart_options",
    "build_dataframe_from_rows",
    "build_overview_dataset",
    "build_table_options",
    "detect_frequency",
    "file_fingerprint",
    "list_excel_sheets",
    "load_dataframe",
    "numeric_variable_names",
    "parse_csv_items",
    "parse_float",
    "parse_hlines",
    "parse_key_value_mapping",
    "parse_shade",
    "parse_vlines",
    "period_bounds",
    "preview_table_frame",
    "read_raw_rows",
    "resolve_position",
    "series_style_widget_key",
    "time_mask",
]
