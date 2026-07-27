"""时间序列图表的延迟应用配置控件。"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

import pandas as pd

PACF_METHODS = ("ywm", "yw", "ols")
GRID_MODE_OPTIONS = {
    "横向网格": "horizontal",
    "纵向网格": "vertical",
    "横纵网格": "both",
}
GRID_LINE_STYLE_OPTIONS = {
    "实线": "solid",
    "虚线": "dashed",
    "点线": "dotted",
    "点划线": "dashdot",
}
STATE_PREFIX = "tools.analysis.chart_config"


def chart_scope(*parts: object) -> str:
    """为页面、数据表、变量和图表类型生成稳定且隔离的配置作用域。"""
    content = "|".join(str(part) for part in parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _state_key(scope: str, name: str) -> str:
    return f"{STATE_PREFIX}.{scope}.{name}"


def get_applied_config(st_obj, scope: str, defaults: dict[str, Any]) -> dict[str, Any]:
    """返回当前图表控件的配置；控件变更将在下一次重跑中立即生效。"""
    config = defaults.copy()
    for name, default in defaults.items():
        value = st_obj.session_state.get(_state_key(scope, name), default)
        if name == "grid_mode":
            config[name] = GRID_MODE_OPTIONS.get(value, value)
        elif name == "grid_line_style":
            config[name] = GRID_LINE_STYLE_OPTIONS.get(value, value)
        else:
            config[name] = value
    return config


def _grid_mode_select(st_obj, scope: str, applied: dict[str, Any]) -> str:
    selected_mode = applied.get("grid_mode", "both")
    labels = list(GRID_MODE_OPTIONS)
    selected_index = list(GRID_MODE_OPTIONS.values()).index(
        selected_mode if selected_mode in GRID_MODE_OPTIONS.values() else "both"
    )
    label = st_obj.selectbox(
        "网格方向",
        options=labels,
        index=selected_index,
        key=_state_key(scope, "grid_mode"),
    )
    return GRID_MODE_OPTIONS[label]


def _grid_line_style_select(st_obj, scope: str, applied: dict[str, Any]) -> str:
    selected_style = applied.get("grid_line_style", "solid")
    labels = list(GRID_LINE_STYLE_OPTIONS)
    selected_index = list(GRID_LINE_STYLE_OPTIONS.values()).index(
        selected_style if selected_style in GRID_LINE_STYLE_OPTIONS.values() else "solid"
    )
    label = st_obj.selectbox(
        "网格线型",
        options=labels,
        index=selected_index,
        key=_state_key(scope, "grid_line_style"),
    )
    return GRID_LINE_STYLE_OPTIONS[label]


def _is_date_value(value: Any) -> bool:
    return isinstance(value, (pd.Timestamp, datetime, date))


def _time_series_axis_options(st_obj, scope: str, applied: dict[str, Any]) -> dict[str, Any]:
    st_obj.markdown("**坐标轴范围与刻度**")
    columns = st_obj.columns(4)
    x_start = applied["x_start"]
    if _is_date_value(x_start):
        x_start = columns[0].date_input(
            "横轴起始日期",
            value=pd.Timestamp(x_start).date(),
            key=_state_key(scope, "x_start"),
        )
    else:
        x_start = columns[0].number_input(
            "横轴起始值",
            value=x_start,
            placeholder="自动",
            key=_state_key(scope, "x_start"),
        )
    max_ticks = columns[1].number_input(
        "横轴刻度数量",
        min_value=2,
        value=int(applied["max_ticks"]),
        step=1,
        key=_state_key(scope, "max_ticks"),
    )
    y_start = columns[2].number_input(
        "纵轴起始值",
        value=applied["y_start"],
        placeholder="自动",
        key=_state_key(scope, "y_start"),
    )
    y_tick_count = columns[3].number_input(
        "纵轴刻度数量",
        min_value=2,
        value=int(applied["y_tick_count"]),
        step=1,
        key=_state_key(scope, "y_tick_count"),
    )
    return {
        "x_start": x_start,
        "y_start": None if y_start is None else float(y_start),
        "max_ticks": int(max_ticks),
        "y_tick_count": int(y_tick_count),
    }


def _correlogram_axis_options(st_obj, scope: str, applied: dict[str, Any]) -> dict[str, Any]:
    st_obj.markdown("**坐标轴范围与刻度**")
    columns = st_obj.columns(4)
    x_start = columns[0].number_input(
        "横轴起始值",
        value=float(applied["x_start"]),
        step=1.0,
        key=_state_key(scope, "x_start"),
    )
    max_ticks = columns[1].number_input(
        "横轴刻度数量",
        min_value=2,
        value=int(applied["max_ticks"]),
        step=1,
        key=_state_key(scope, "max_ticks"),
    )
    y_start = columns[2].number_input(
        "纵轴起始值",
        value=applied["y_start"],
        placeholder="自动",
        key=_state_key(scope, "y_start"),
    )
    y_tick_count = columns[3].number_input(
        "纵轴刻度数量",
        min_value=2,
        value=int(applied["y_tick_count"]),
        step=1,
        key=_state_key(scope, "y_tick_count"),
    )
    return {
        "x_start": float(x_start),
        "y_start": None if y_start is None else float(y_start),
        "max_ticks": int(max_ticks),
        "y_tick_count": int(y_tick_count),
    }


def render_time_series_config_expander(
    st_obj,
    *,
    scope: str,
    defaults: dict[str, Any],
) -> None:
    """渲染时间序列图下方的即时生效配置。"""
    applied = get_applied_config(st_obj, scope, defaults)
    with st_obj.expander("图表设置", expanded=False):
        st_obj.markdown("**标题**")
        title_columns = st_obj.columns(3)
        title_columns[0].text_input(
            "图片标题", applied["title"], key=_state_key(scope, "title")
        )
        title_columns[1].text_input(
            "横轴标题", applied["x_title"], key=_state_key(scope, "x_title")
        )
        title_columns[2].text_input(
            "纵轴标题", applied["y_title"], key=_state_key(scope, "y_title")
        )
        _time_series_axis_options(st_obj, scope, applied)

        st_obj.markdown("**图形样式**")
        style_columns = st_obj.columns(4)
        style_columns[0].number_input(
            "线宽",
            min_value=0.1,
            value=float(applied["line_width"]),
            step=0.1,
            key=_state_key(scope, "line_width"),
        )
        style_columns[1].number_input(
            "点大小",
            min_value=0.0,
            value=float(applied["marker_size"]),
            step=0.5,
            key=_state_key(scope, "marker_size"),
        )
        with style_columns[2]:
            _grid_mode_select(st_obj, scope, applied)
        with style_columns[3]:
            _grid_line_style_select(st_obj, scope, applied)


def render_correlogram_config_expander(
    st_obj,
    *,
    scope: str,
    defaults: dict[str, Any],
    maximum_lags: int,
) -> None:
    """渲染 ACF/PACF 组合图下方的即时生效配置。"""
    applied = get_applied_config(st_obj, scope, defaults)
    with st_obj.expander("ACF/PACF 图表设置", expanded=False):
        st_obj.markdown("**标题**")
        title_columns = st_obj.columns(2)
        title_columns[0].text_input(
            "ACF 图片标题", applied["acf_title"], key=_state_key(scope, "acf_title")
        )
        title_columns[1].text_input(
            "PACF 图片标题", applied["pacf_title"], key=_state_key(scope, "pacf_title")
        )
        st_obj.markdown("**轴标题**")
        axis_title_columns = st_obj.columns(4)
        axis_title_columns[0].text_input(
            "ACF 横轴标题", applied["acf_x_title"], key=_state_key(scope, "acf_x_title")
        )
        axis_title_columns[1].text_input(
            "ACF 纵轴标题", applied["acf_y_title"], key=_state_key(scope, "acf_y_title")
        )
        axis_title_columns[2].text_input(
            "PACF 横轴标题", applied["pacf_x_title"], key=_state_key(scope, "pacf_x_title")
        )
        axis_title_columns[3].text_input(
            "PACF 纵轴标题", applied["pacf_y_title"], key=_state_key(scope, "pacf_y_title")
        )
        _correlogram_axis_options(st_obj, scope, applied)

        st_obj.markdown("**图形样式**")
        option_columns = st_obj.columns(4)
        option_columns[0].number_input(
            "滞后阶数",
            min_value=1,
            max_value=maximum_lags,
            value=min(int(applied["nlags"]), maximum_lags),
            step=1,
            key=_state_key(scope, "nlags"),
        )
        option_columns[1].selectbox(
            "PACF 计算方法",
            options=PACF_METHODS,
            index=PACF_METHODS.index(applied["pacf_method"]),
            key=_state_key(scope, "pacf_method"),
        )
        with option_columns[2]:
            _grid_mode_select(st_obj, scope, applied)
        with option_columns[3]:
            _grid_line_style_select(st_obj, scope, applied)


__all__ = [
    "chart_scope",
    "get_applied_config",
    "render_correlogram_config_expander",
    "render_time_series_config_expander",
]
