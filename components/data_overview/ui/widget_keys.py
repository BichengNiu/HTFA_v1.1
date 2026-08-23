"""数据概览的 Streamlit widget 键（按域拆分、按前缀生成）。

换文件或换变量时这些键会被清除，避免旧 widget 值被 Streamlit 自动
恢复。不同实例用不同 key_prefix 生成隔离的键集合，例如
``overview_widget_keys("dfm")``。
"""

from __future__ import annotations

# 选择器键名（变量多选；工作表键在 dataset 构建后渲染，故意不清理）。
_SELECTOR_KEY_NAMES = (
    "vars",
)

# 数据读取设置键名。
_READ_KEY_NAMES = (
    "variable_name_row",
    "data_start_row",
    "time_column",
)

# 数据表高级选项键名（筛选/时间/视图）。
_TABLE_KEY_NAMES = (
    "filter_col",
    "filter_op",
    "filter_val",
    "time_preset",
    "time_start",
    "time_end",
    "view_mode",
    "view_rows",
)

# 图形高级选项键名（5-tab 全部控件）。
_CHART_KEY_NAMES = (
    "chart_options_expander",
    "title",
    "note",
    "note_loc",
    "note_prefix",
    "title_pos",
    "title_pad",
    "xtitle",
    "xtitle_loc",
    "ytitle",
    "ytitle_pos",
    "ymin",
    "xmin",
    "ytick_count",
    "ylabel_count",
    "xtick_count",
    "xlabel_count",
    "max_ticks",
    "year_ruler",
    "linewidth",
    "markersize",
    "marker_edge",
    "grid_style",
    "grid_width",
    "grid_linestyle",
    "legend",
    "legend_loc",
    "legend_labels",
    "legend_bbox_x",
    "legend_bbox_y",
    "legend_title",
    "legend_cols",
    "legend_size",
    "aspect",
    "width",
    "height",
    "facet",
    "facet_rows",
    "facet_cols",
    "sharex",
    "sharey",
    "auto_dual_y",
    "scale_ratio_threshold",
    "axis_groups",
    "max_y_axes",
    "second_axis_on",
    "third_axis_on",
    "second_axis",
    "third_axis",
    "second_axis_title",
    "third_axis_title",
    "log_vars",
    "unit",
    "units",
    "colors",
    "show_values",
    "value_decimals",
    "shade_alpha",
    "shade_color",
    "vlines",
    "hlines",
    "vline_color",
    "vline_style",
    "vline_linewidth",
    "hline_color",
    "hline_style",
    "hline_linewidth",
    "shade",
)


def selector_widget_keys(prefix: str = "sarimax") -> tuple[str, ...]:
    """选择器键（变量多选）。"""
    return tuple(f"{prefix}_preview_{name}" for name in _SELECTOR_KEY_NAMES)


def read_widget_keys(prefix: str = "sarimax") -> tuple[str, ...]:
    """数据读取设置键（变量名行、数据开始行与时间列）。"""
    return tuple(f"{prefix}_preview_{name}" for name in _READ_KEY_NAMES)


def table_widget_keys(prefix: str = "sarimax") -> tuple[str, ...]:
    """数据表高级选项键。"""
    return tuple(f"{prefix}_table_{name}" for name in _TABLE_KEY_NAMES)


def chart_widget_keys(prefix: str = "sarimax") -> tuple[str, ...]:
    """图形高级选项键。"""
    return tuple(f"{prefix}_preview_{name}" for name in _CHART_KEY_NAMES)


def overview_widget_keys(prefix: str = "sarimax") -> tuple[str, ...]:
    """数据预览全部键（选择器在前，读取设置紧随其后）。"""
    return (
        selector_widget_keys(prefix)
        + read_widget_keys(prefix)
        + chart_widget_keys(prefix)
        + table_widget_keys(prefix)
    )


def preview_key(prefix: str, name: str) -> str:
    """拼装 ``{prefix}_preview_{name}`` 形式的键。"""
    return f"{prefix}_preview_{name}"


def table_key(prefix: str, name: str) -> str:
    """拼装 ``{prefix}_table_{name}`` 形式的键。"""
    return f"{prefix}_table_{name}"


# 默认（sarimax）实例的键集合。
SELECTOR_WIDGET_KEYS = selector_widget_keys()
READ_WIDGET_KEYS = read_widget_keys()
TABLE_WIDGET_KEYS = table_widget_keys()
CHART_WIDGET_KEYS = chart_widget_keys()


__all__ = [
    "CHART_WIDGET_KEYS",
    "READ_WIDGET_KEYS",
    "SELECTOR_WIDGET_KEYS",
    "TABLE_WIDGET_KEYS",
    "chart_widget_keys",
    "overview_widget_keys",
    "preview_key",
    "read_widget_keys",
    "selector_widget_keys",
    "table_key",
    "table_widget_keys",
]
