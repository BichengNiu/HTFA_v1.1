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
)
from .parsing import (
    detect_frequency,
    parse_float,
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
    "parse_float",
    "parse_shade",
    "parse_vlines",
    "period_bounds",
    "preview_table_frame",
    "resolve_position",
    "time_mask",
]
