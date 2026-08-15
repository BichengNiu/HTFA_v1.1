"""共享数据集的原始变量概览页。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from dashboard.core.ui.utils.chart_legend import place_chart_legend_at_bottom
from dashboard.explore.analysis.stationarity import (
    create_time_series_figure,
    matplotlib_date_compatibility,
    numeric_variable_names,
    prepare_selected_series,
    summarize_series,
)
from dashboard.explore.core.constants import FREQUENCY_DISPLAY_NAMES
from dashboard.explore.core.data_source import (
    format_table_option,
)
from dashboard.explore.ui.chart_controls import (
    chart_scope,
    get_applied_config,
    render_correlogram_chart,
    render_time_series_config_expander,
)
from dashboard.explore.ui.dataset_context import get_explore_dataset
from dashboard.explore.ui.stationarity import resolve_table_frequency


def _render_series_status(
    st_obj,
    series: pd.Series,
    frequency: str,
    time_label: str | None,
    updated_at: str,
) -> None:
    columns = st_obj.columns(5)
    columns[0].metric("总观测数", f"{len(series):,}")
    columns[1].metric("有效观测数", f"{series.notna().sum():,}")
    columns[2].metric("缺失值", f"{series.isna().sum():,}")
    columns[3].metric("识别频率", FREQUENCY_DISPLAY_NAMES.get(frequency, "未确定"))
    columns[4].metric("更新日期", updated_at)
    if isinstance(series.index, pd.DatetimeIndex):
        st_obj.caption(
            f"时间轴：{time_label or '时间索引'}；"
            f"{series.index.min():%Y-%m-%d} 至 {series.index.max():%Y-%m-%d}"
        )
    else:
        st_obj.warning("未识别到时间列，当前按行位置绘图。")


def _render_correlogram(
    st_obj,
    series: pd.Series,
    variable: str,
    *,
    scope: str,
) -> None:
    render_correlogram_chart(
        st_obj,
        series,
        title_prefix=f"{variable} · 原始序列",
        include_acf=True,
        include_pacf=True,
        alpha=0.05,
        scope=scope,
    )


def render_data_overview(st_obj, uploaded_file, *, dataset=None) -> None:
    """渲染原始变量的时间序列、统计摘要与相关结构。"""
    if uploaded_file is None:
        st_obj.info("请先在侧边栏上传共享数据集。")
        return

    try:
        dataset = dataset or get_explore_dataset(st_obj, uploaded_file)
    except Exception as exc:  # noqa: BLE001 - user-facing file load boundary
        st_obj.error(f"文件读取或数据库解析失败：{exc}")
        return

    tables = dataset.tables
    if not tables:
        st_obj.error("数据集没有可分析的数据表。")
        return

    table_column, variable_column = st_obj.columns(2)
    table_key = table_column.selectbox(
        "选择数据表",
        options=list(tables),
        format_func=lambda key: format_table_option(key, tables),
        key="data_overview_table_select",
    )
    data = tables[table_key]
    variables = numeric_variable_names(data)
    if not variables:
        st_obj.error("所选数据表没有实数型变量。")
        return
    variable = variable_column.selectbox(
        "选择变量",
        options=variables,
        key="data_overview_variable_select",
    )

    try:
        series, time_label = prepare_selected_series(data, variable)
    except Exception as exc:  # noqa: BLE001 - user-facing selection boundary
        st_obj.error(f"变量准备失败：{exc}")
        return

    frequency = resolve_table_frequency(table_key, series)
    metadata = dataset.metadata_map.get(variable)
    updated_at = getattr(metadata, "updated_at", None) or "未提供"
    _render_series_status(
        st_obj,
        series,
        frequency,
        time_label,
        updated_at,
    )

    plot_column, summary_column = st_obj.columns([1.35, 1])
    with plot_column:
        try:
            time_scope = chart_scope("data_overview", table_key, variable, "time_series")
            time_defaults = {
                "title": f"{variable} · 原始序列",
                "x_title": "时间",
                "y_title": str(series.name or "数值"),
                "line_width": 3.0,
                "marker_size": 0.0,
                "max_ticks": 12,
                "y_tick_count": 8,
                "x_start": (
                    series.index.min().date()
                    if isinstance(series.index, pd.DatetimeIndex)
                    else None
                ),
                "y_start": None,
                "grid_mode": "both",
                "grid_line_style": "solid",
            }
            config = get_applied_config(st_obj, time_scope, time_defaults)
            with matplotlib_date_compatibility():
                figure = create_time_series_figure(series, **config)
                try:
                    st_obj.pyplot(
                        place_chart_legend_at_bottom(figure),
                        width="stretch",
                        clear_figure=True,
                    )
                finally:
                    plt.close(figure)
            render_time_series_config_expander(
                st_obj,
                scope=time_scope,
                defaults=time_defaults,
            )
        except Exception as exc:  # noqa: BLE001 - optional chart render boundary
            st_obj.warning(f"原始序列图无法绘制：{exc}")
    with summary_column:
        try:
            st_obj.code(
                summarize_series(series, frequency=frequency),
                language=None,
            )
        except Exception as exc:  # noqa: BLE001 - optional summary render boundary
            st_obj.warning(f"Ts 统计摘要无法生成：{exc}")

    _render_correlogram(
        st_obj,
        series,
        variable,
        scope=chart_scope("data_overview", table_key, variable, "correlogram"),
    )


__all__ = ["render_data_overview"]
