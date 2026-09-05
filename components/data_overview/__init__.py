"""可移植的数据概览组件。

顶层名称构成可移植组件的公开入口，并通过 ``__getattr__`` 延迟加载实现层。
这样，``data_overview.core`` 的纯解析入口不会因为执行包初始化而加载
Streamlit 或 UI 模块；需要渲染时仍可从组件顶层导入公开对象。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "OverviewDataset": (".core", "OverviewDataset"),
    "build_chart_options": (".core", "build_chart_options"),
    "build_overview_dataset": (".core", "build_overview_dataset"),
    "build_table_options": (".core", "build_table_options"),
    "detect_frequency": (".core", "detect_frequency"),
    "numeric_variable_names": (".core", "numeric_variable_names"),
    "parse_float": (".core", "parse_float"),
    "parse_hlines": (".core", "parse_hlines"),
    "parse_shade": (".core", "parse_shade"),
    "parse_vlines": (".core", "parse_vlines"),
    "period_bounds": (".core", "period_bounds"),
    "preview_table_frame": (".core", "preview_table_frame"),
    "resolve_position": (".core", "resolve_position"),
    "series_style_widget_key": (".core", "series_style_widget_key"),
    "time_mask": (".core", "time_mask"),
    "DataOverview": (".ui", "DataOverview"),
    "DataOverviewConfig": (".ui", "DataOverviewConfig"),
    "DatasetProcessor": (".ui", "DatasetProcessor"),
    "create_data_overview": (".ui", "create_data_overview"),
    "BuiltinDataSource": (".ui.data_source", "BuiltinDataSource"),
    "DataSource": (".ui.data_source", "DataSource"),
    "place_chart_legend_at_bottom": (
        ".ui.legend",
        "place_chart_legend_at_bottom",
    ),
    "render_pyplot_figure": (".ui.legend", "render_pyplot_figure"),
    "chart_widget_keys": (".ui.widget_keys", "chart_widget_keys"),
    "overview_widget_keys": (".ui.widget_keys", "overview_widget_keys"),
    "preview_key": (".ui.widget_keys", "preview_key"),
    "read_widget_keys": (".ui.widget_keys", "read_widget_keys"),
    "selector_widget_keys": (".ui.widget_keys", "selector_widget_keys"),
    "table_key": (".ui.widget_keys", "table_key"),
    "table_widget_keys": (".ui.widget_keys", "table_widget_keys"),
}


def __getattr__(name: str) -> Any:
    """按需加载公共名称，避免纯逻辑导入触发 UI 初始化。"""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """让交互式工具仍能发现所有延迟加载的公共名称。"""
    return sorted(set(globals()) | set(_EXPORTS))


__version__ = "1.0.0"

__all__ = [
    "BuiltinDataSource",
    "DataOverview",
    "DataOverviewConfig",
    "DataSource",
    "DatasetProcessor",
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
    "selector_widget_keys",
    "series_style_widget_key",
    "table_key",
    "table_widget_keys",
    "time_mask",
]
