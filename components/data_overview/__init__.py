"""data_overview —— 可移植的数据概览 Streamlit 组件。

用法::

    from data_overview import create_data_overview

    overview = create_data_overview(
        key_prefix="dfm",                 # widget 键前缀（默认 "sarimax"）
        state_namespace="model_analysis.dfm",  # dataset 缓存命名空间
    )
    overview(st_obj)                      # 渲染整段（上传→选择→表/图→高级选项）

纯函数与解析器也可直接导入::

    from data_overview import (
        build_chart_options,   # 状态 → Ts plot_series 参数（含中文枚举映射）
        parse_vlines,          # 参考线解析（行号/日期）
        draw_series_plot,      # Ts plot_series 渲染收口
    )
"""

from .core import (
    OverviewDataset,
    build_chart_options,
    build_overview_dataset,
    build_table_options,
    detect_frequency,
    numeric_variable_names,
    parse_float,
    parse_hlines,
    parse_shade,
    parse_vlines,
    period_bounds,
    preview_table_frame,
    resolve_position,
    series_style_widget_key,
    time_mask,
)
from .ui import DataOverview, DataOverviewConfig, create_data_overview
from .ui.data_source import BuiltinDataSource, DataSource
from .ui.legend import place_chart_legend_at_bottom, render_pyplot_figure
from .ui.widget_keys import (
    chart_widget_keys,
    overview_widget_keys,
    preview_key,
    read_widget_keys,
    selector_widget_keys,
    table_key,
    table_widget_keys,
)

__version__ = "1.0.0"

__all__ = [
    "BuiltinDataSource",
    "DataOverview",
    "DataOverviewConfig",
    "DataSource",
    "OverviewDataset",
    "build_chart_options",
    "build_overview_dataset",
    "build_table_options",
    "chart_widget_keys",
    "create_data_overview",
    "detect_frequency",
    "numeric_variable_names",
    "overview_widget_keys",
    "parse_float",
    "parse_hlines",
    "parse_shade",
    "parse_vlines",
    "period_bounds",
    "place_chart_legend_at_bottom",
    "preview_key",
    "preview_table_frame",
    "read_widget_keys",
    "render_pyplot_figure",
    "resolve_position",
    "series_style_widget_key",
    "selector_widget_keys",
    "table_key",
    "table_widget_keys",
    "time_mask",
]
