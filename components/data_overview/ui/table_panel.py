"""数据概览的表侧面板：预览表 + 视图开关 + 行数信息 + 数据表高级选项。

「数据表高级选项」expander 内的筛选条件经 session_state 直接作用于
上方的预览表（expander 内不再重复展示结果表），这里只渲染控件与
统计量表。
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..core.constants import FILTER_OPERATORS, TIME_PRESETS
from ..core.options import build_table_options, preview_table_frame
from ..core.parsing import detect_frequency
from .selectors import render_view_toggles
from .widget_keys import table_key


def render_time_filter(st_obj, dataset, *, key_prefix: str = "sarimax") -> None:
    """按数据频率渲染时间筛选：预设快捷范围 + 自定义起止（粒度匹配）。"""
    time_series = pd.to_datetime(dataset.frame[dataset.time_column])
    freq = detect_frequency(time_series)
    presets = TIME_PRESETS[freq]
    labels = [label for label, _ in presets]
    st_obj.selectbox(
        "时间范围",
        options=labels,
        key=table_key(key_prefix, "time_preset"),
        help=(
            f"数据为{freq}频率；快捷范围按最近期数计算，"
            f"自定义范围只能选择到{freq}粒度，且限定在数据范围内。"
        ),
    )
    preset_label = st.session_state.get(table_key(key_prefix, "time_preset"))
    if preset_label != "自定义":
        st.session_state.pop(table_key(key_prefix, "time_start"), None)
        st.session_state.pop(table_key(key_prefix, "time_end"), None)
        return

    if freq == "year":
        years = sorted(time_series.dt.year.unique().astype(str))
        row = st_obj.columns(2)
        row[0].selectbox(
            "起始年", options=years, key=table_key(key_prefix, "time_start")
        )
        row[1].selectbox(
            "结束年",
            options=years,
            index=len(years) - 1,
            key=table_key(key_prefix, "time_end"),
        )
    elif freq == "quarter":
        quarters = sorted(time_series.dt.to_period("Q").astype(str).unique())
        row = st_obj.columns(2)
        row[0].selectbox(
            "起始季度", options=quarters, key=table_key(key_prefix, "time_start")
        )
        row[1].selectbox(
            "结束季度",
            options=quarters,
            index=len(quarters) - 1,
            key=table_key(key_prefix, "time_end"),
        )
    elif freq == "month":
        months = sorted(time_series.dt.strftime("%Y-%m").unique())
        row = st_obj.columns(2)
        row[0].selectbox(
            "起始年月", options=months, key=table_key(key_prefix, "time_start")
        )
        row[1].selectbox(
            "结束年月",
            options=months,
            index=len(months) - 1,
            key=table_key(key_prefix, "time_end"),
        )
    else:  # week / day：日期控件限定在数据范围内
        date_min = time_series.min().date()
        date_max = time_series.max().date()
        row = st_obj.columns(2)
        row[0].date_input(
            "起始日期",
            value=date_min,
            min_value=date_min,
            max_value=date_max,
            key=table_key(key_prefix, "time_start"),
        )
        row[1].date_input(
            "结束日期",
            value=date_max,
            min_value=date_min,
            max_value=date_max,
            key=table_key(key_prefix, "time_end"),
        )


def render_table_options_expander(
    st_obj, dataset, selected: list[str], *, key_prefix: str = "sarimax"
) -> None:
    """数据表高级选项：筛选条件与统计量。"""
    frame = dataset.frame
    with st_obj.expander("数据表高级选项", expanded=False):
        # 筛选条件。
        row = st_obj.columns(3)
        row[0].selectbox(
            "筛选列",
            options=["无"] + list(selected),
            key=table_key(key_prefix, "filter_col"),
            help="选择要按数值条件筛选的列；选择“无”表示不筛选。",
        )
        row[1].selectbox(
            "条件",
            options=list(FILTER_OPERATORS),
            index=0,
            key=table_key(key_prefix, "filter_op"),
        )
        row[2].number_input(
            "阈值",
            value=0.0,
            key=table_key(key_prefix, "filter_val"),
        )

        if dataset.time_column is not None:
            render_time_filter(st_obj, dataset, key_prefix=key_prefix)

        # 当前筛选掩码（与上方预览表一致），用于统计量。
        table_state = build_table_options(
            st.session_state, dataset, key_prefix=key_prefix
        )
        result = frame.loc[table_state["mask"]]

        numeric_columns = [name for name in selected if name in result.columns]
        if numeric_columns:
            stats = result[numeric_columns].describe().T
            # 默认保留两位小数；count 保持整数显示。
            column_config = {
                column: st_obj.column_config.NumberColumn(format="%.2f")
                for column in stats.columns
                if column != "count"
            }
            column_config["count"] = st_obj.column_config.NumberColumn(format="%d")
            st_obj.dataframe(
                stats,
                width="stretch",
                column_config=column_config,
            )


def render_table_panel(
    st_obj,
    dataset,
    selected: list[str],
    filtered,
    table_state: dict,
    *,
    key_prefix: str = "sarimax",
) -> None:
    """渲染左栏：预览表 + 视图开关 + 当前筛选行数信息。

    filtered：筛选后的数据框（table_state["mask"] 已应用）；
    table_state：build_table_options 的输出（view/mask）。
    """
    table_columns = list(selected)
    if dataset.time_column is not None:
        table_columns = [dataset.time_column, *table_columns]
    preview_frame = preview_table_frame(
        dataset, filtered, table_state["view"], table_columns
    )
    st_obj.dataframe(
        preview_frame,
        width="stretch",
    )
    render_view_toggles(st_obj, key_prefix=key_prefix)
    st_obj.caption(
        f"当前筛选：{len(filtered):,} 行 / 共 {len(dataset.frame):,} 行"
    )


__all__ = [
    "render_table_options_expander",
    "render_table_panel",
    "render_time_filter",
]
