"""数据概览 UI 的 Streamlit widget 键集合（按域拆分，供 state.py 汇总）。

换文件或换变量时这些键会被清除，避免旧 widget 值被 Streamlit 自动
恢复；训练/分析/预测环节的键仍声明在 ui/state.py。
"""

from __future__ import annotations

# 选择器（变量多选；工作表键在 dataset 构建后渲染，故意不清理）。
SELECTOR_WIDGET_KEYS = (
    "sarimax_preview_vars",
)

# 数据表高级选项（筛选/时间/视图）。
TABLE_WIDGET_KEYS = (
    "sarimax_table_filter_col",
    "sarimax_table_filter_op",
    "sarimax_table_filter_val",
    "sarimax_table_time_preset",
    "sarimax_table_time_start",
    "sarimax_table_time_end",
    "sarimax_table_view_head",
    "sarimax_table_view_tail",
)

# 图形高级选项（5-tab 全部控件）。
CHART_WIDGET_KEYS = (
    "sarimax_preview_title",
    "sarimax_preview_note",
    "sarimax_preview_note_loc",
    "sarimax_preview_note_prefix",
    "sarimax_preview_title_pos",
    "sarimax_preview_xtitle",
    "sarimax_preview_xtitle_loc",
    "sarimax_preview_ytitle",
    "sarimax_preview_ytitle_pos",
    "sarimax_preview_ymin",
    "sarimax_preview_xmin",
    "sarimax_preview_ytick_count",
    "sarimax_preview_ylabel_count",
    "sarimax_preview_xtick_count",
    "sarimax_preview_xlabel_count",
    "sarimax_preview_year_ruler",
    "sarimax_preview_linewidth",
    "sarimax_preview_markersize",
    "sarimax_preview_marker_edge",
    "sarimax_preview_grid_style",
    "sarimax_preview_grid_width",
    "sarimax_preview_grid_linestyle",
    "sarimax_preview_legend",
    "sarimax_preview_legend_loc",
    "sarimax_preview_legend_title",
    "sarimax_preview_legend_cols",
    "sarimax_preview_aspect",
    "sarimax_preview_width",
    "sarimax_preview_height",
    "sarimax_preview_facet",
    "sarimax_preview_facet_rows",
    "sarimax_preview_facet_cols",
    "sarimax_preview_sharey",
    "sarimax_preview_second_axis_on",
    "sarimax_preview_third_axis_on",
    "sarimax_preview_second_axis",
    "sarimax_preview_third_axis",
    "sarimax_preview_second_axis_title",
    "sarimax_preview_third_axis_title",
    "sarimax_preview_log_vars",
    "sarimax_preview_show_values",
    "sarimax_preview_value_decimals",
    "sarimax_preview_shade_alpha",
    "sarimax_preview_shade_color",
    "sarimax_preview_vlines",
    "sarimax_preview_vline_color",
    "sarimax_preview_vline_style",
    "sarimax_preview_shade",
)


__all__ = [
    "CHART_WIDGET_KEYS",
    "SELECTOR_WIDGET_KEYS",
    "TABLE_WIDGET_KEYS",
]
