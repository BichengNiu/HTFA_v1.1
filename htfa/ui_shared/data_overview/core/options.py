"""数据概览的选项构建层：会话状态 → 表格/绘图参数（纯函数）。

build_* 系列输入为状态映射（如 st.session_state），不直接依赖
streamlit，可脱离 UI 单测；输出与 Ts plot_series 签名一一对应
（由 tests/test_options.py 断言）。key_prefix 参数隔离不同实例
的 widget 键（默认 "sarimax" 与历史行为一致）。
"""

from __future__ import annotations

import hashlib

import pandas as pd
from Ts.TsPlots.style import DEFAULT_LINESTYLES, DEFAULT_MARKERS, DEFAULT_PALETTE

from .constants import (
    COLOR_HEX_MAP,
    FILTER_OPERATORS,
    GRID_STYLE_MAP,
    NOTE_LOCATION_MAP,
    PREVIEW_TABLE_ROWS,
    TITLE_POSITION_MAP,
    XTITLE_LOCATION_MAP,
    YTITLE_POSITION_MAP,
)
from .parsing import (
    parse_csv_items,
    parse_float,
    parse_hlines,
    parse_key_value_mapping,
    parse_shade,
    parse_vlines,
    time_mask,
)


def _get(state, key: str, default):
    value = state.get(key, default)
    return default if value is None else value


def build_table_options(state, dataset, *, key_prefix: str = "sarimax") -> dict:
    """从状态读取数据表高级选项的当前筛选与视图状态。

    预览表在 expander 之前渲染，控件值需经 session_state 读取；
    首次运行（控件尚未渲染）时回退到与控件默认值一致的默认参数。
    返回 dict：mask（布尔筛选掩码）、view（head/tail/all）和
    view_rows（行数；all 视图为 None）。
    """

    def get(name: str, default):
        return _get(state, f"{key_prefix}_table_{name}", default)

    view_mode = get("view_mode", "显示头10行")

    frame = dataset.frame
    mask = pd.Series(True, index=frame.index)
    filter_col = get("filter_col", "无")
    filter_op = get("filter_op", "≥")
    filter_val = float(get("filter_val", 0.0))
    if filter_col != "无":
        mask &= getattr(frame[filter_col], FILTER_OPERATORS[filter_op])(
            filter_val
        )
    if dataset.time_column is not None:
        mask &= time_mask(dataset, state, key_prefix=key_prefix)

    if view_mode == "显示尾10行":
        view = "tail"
        view_rows = PREVIEW_TABLE_ROWS
    elif view_mode == "显示全部":
        view = "all"
        view_rows = None
    elif view_mode == "显示指定行数":
        view = "head"
        view_rows = max(1, int(get("view_rows", PREVIEW_TABLE_ROWS)))
    else:
        view = "head"
        view_rows = PREVIEW_TABLE_ROWS
    return {"mask": mask, "view": view, "view_rows": view_rows}


def preview_table_frame(
    dataset,
    filtered,
    view: str,
    table_columns: list[str],
    row_count: int | None = None,
) -> pd.DataFrame:
    """构建预览表内容：按视图取头/尾/全部，时间列转字符串显示。

    时间列转为字符串显示（YYYY-MM-DD）：Streamlit 1.61 前端
    statistics 对 datetime 列存在微秒/纳秒单位换算 bug（min 会
    显示为错误年份），字符串列走文本统计，显示正确的最小日期。
    """
    rows = PREVIEW_TABLE_ROWS if row_count is None else max(1, int(row_count))
    if view == "tail":
        preview_frame = filtered.tail(rows)
    elif view == "all":
        preview_frame = filtered
    else:
        preview_frame = filtered.head(rows)
    preview_frame = preview_frame.loc[:, table_columns]
    if dataset.time_column is not None:
        preview_frame = preview_frame.copy()
        preview_frame[dataset.time_column] = preview_frame[
            dataset.time_column
        ].dt.strftime("%Y-%m-%d")
    return preview_frame


def trim_to_valid_range(frame: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    """裁剪到变量有效观测的首尾范围，并保留中间缺失值。

    多变量传入时使用所有变量的联合有效范围；单变量传入时得到该
    变量自己的时间范围。只移除首个有效值之前和末个有效值之后的
    行，不压缩中间缺失的时间位置。
    """
    if not variables or frame.empty:
        return frame

    valid_mask = frame.loc[:, variables].notna().any(axis=1)
    valid_positions = valid_mask.to_numpy().nonzero()[0]
    if len(valid_positions) == 0:
        return frame.iloc[0:0]
    return frame.iloc[valid_positions[0] : valid_positions[-1] + 1]


def series_style_widget_key(prefix: str, variable: str, field: str) -> str:
    """返回按变量稳定隔离的逐序列样式控件键。"""
    digest = hashlib.sha1(str(variable).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_preview_series_style_{digest}_{field}"


def build_chart_options(
    state,
    dataset,
    filtered,
    *,
    variables: list[str] | None = None,
    key_prefix: str = "sarimax",
) -> tuple[dict, list[str]]:
    """从状态读取图形高级选项控件的当前值，构建绘图参数。

    绘图在 expander 之前渲染，控件值需经 session_state 读取；
    首次运行（控件尚未渲染）时回退到与控件默认值一致的默认参数。
    filtered：当前筛选后的数据框（与绘图一致），参考线与阴影的
    行序号按它换算为 X 轴位置。
    variables：当前选中的变量顺序，用于校验颜色、图例标签与映射输入。
    返回 (绘图参数 dict, 解析错误列表)。输出键与 Ts plot_series
    参数一一对应；data/x/y/ax 等适配器内部参数不在此返回。
    """

    def get(name: str, default):
        return _get(state, f"{key_prefix}_preview_{name}", default)

    selected_variables = list(
        variables
        if variables is not None
        else state.get(f"{key_prefix}_preview_vars", []) or []
    )

    # 三个标题（图/X/Y）均为常显输入框：填写才显示，留空不显示。
    # X 轴标题留空必须传 ""（而非 None）：None 会触发绘图层的
    # 兼容路径自动使用时间列名，违背"填写才显示"。
    title = get("title", "") or None
    note = get("note", "") or None
    xtitle = get("xtitle", "")
    ytitle = get("ytitle", "") or None

    # X 轴位置序列（按当前筛选后的数据计，与绘图一致）：
    # 参考线/阴影按行号或日期解析时都需要它。
    chart_frame = trim_to_valid_range(filtered, selected_variables)
    x_values = (
        chart_frame[dataset.time_column]
        if dataset.time_column is not None
        else chart_frame.index
    )

    vlines_text = get("vlines", "")
    hlines_text = get("hlines", "")
    shade_text = get("shade", "")
    vlines, vlines_error = parse_vlines(vlines_text, x_values)
    hlines, hlines_error = parse_hlines(hlines_text)
    shade, shade_error = parse_shade(shade_text, x_values)
    errors = [
        error for error in (vlines_error, hlines_error, shade_error) if error
    ]

    show_legend = bool(get("legend", True))
    expected_count = len(selected_variables) or None
    if show_legend:
        legend_labels, legend_labels_error = parse_csv_items(
            get("legend_labels", ""),
            "自定义图例标签",
            expected_count=expected_count,
        )
    else:
        legend_labels, legend_labels_error = None, None
    axis_groups, axis_groups_error = parse_key_value_mapping(
        get("axis_groups", ""),
        "显式轴分组",
        allowed_keys=selected_variables or None,
    )
    units, units_error = parse_key_value_mapping(
        get("units", ""),
        "变量单位",
        allowed_keys=selected_variables or None,
    )
    errors.extend(
        error
        for error in (
            legend_labels_error,
            axis_groups_error,
            units_error,
        )
        if error
    )

    legend_location = get("legend_loc", "best")
    legend_bbox = None
    if show_legend and legend_location != "best":
        bbox_x_text = str(get("legend_bbox_x", "") or "").strip()
        bbox_y_text = str(get("legend_bbox_y", "") or "").strip()
        if not bbox_x_text and not bbox_y_text:
            bbox_x = bbox_y = None
        else:
            bbox_x = parse_float(bbox_x_text)
            bbox_y = parse_float(bbox_y_text)
        if bool(bbox_x_text) != bool(bbox_y_text) or (
            (bbox_x_text or bbox_y_text)
            and (bbox_x is None or bbox_y is None)
        ):
            errors.append("图例锚点 X/Y 必须填写有效数字")
        elif bbox_x is not None and bbox_y is not None:
            legend_bbox = (bbox_x, bbox_y)

    legend_size = None
    if show_legend:
        legend_size_value = get("legend_size", None)
        if legend_size_value not in (None, ""):
            legend_size = parse_float(str(legend_size_value))
            if legend_size is None or legend_size <= 0:
                errors.append("图例字号必须填写正数")

    # X 轴起点：时间轴解析为日期（Timestamp），数值轴解析为数字。
    xmin_text = get("xmin", "").strip()
    if xmin_text:
        if dataset.time_column is not None:
            try:
                xmin_value = pd.to_datetime(xmin_text)
            except (ValueError, TypeError):
                xmin_value = None
                errors.append(f"X 轴起点无法解析为日期：{xmin_text}")
        else:
            xmin_value = parse_float(xmin_text)
            if xmin_value is None:
                errors.append(f"X 轴起点无法解析为数字：{xmin_text}")
    else:
        xmin_value = None

    grid_on, grid_axis = GRID_STYLE_MAP.get(
        get("grid_style", "纵横网格"), (True, "both")
    )
    grid_linewidth = float(get("grid_width", 0.6))
    grid_linestyle = get("grid_linestyle", "--")

    series_styles = {}
    for index, variable in enumerate(selected_variables):
        def style_get(field, default):
            key = series_style_widget_key(key_prefix, variable, field)
            return state[key] if key in state else default

        series_styles[variable] = {
            "color": style_get(
                "color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]
            ),
            "linestyle": style_get(
                "linestyle",
                DEFAULT_LINESTYLES[index % len(DEFAULT_LINESTYLES)],
            ),
            "marker": style_get(
                "marker", DEFAULT_MARKERS[index % len(DEFAULT_MARKERS)]
            ),
            "linewidth": float(style_get("linewidth", 1.5)),
            "markersize": float(style_get("markersize", 0)),
            "marker_edge_width": float(style_get("marker_edge", 2.5)),
        }
    series_colors = [
        series_styles[variable]["color"] for variable in selected_variables
    ] or None

    return (
        {
            "title": title or None,
            "xtitle": xtitle,
            "ytitle": ytitle,
            "ymin": parse_float(get("ymin", "")),
            "xmin": xmin_value,
            "ytick_count": int(get("ytick_count", 0)),
            "ylabel_count": int(get("ylabel_count", 5)),
            "xtick_count": int(get("xtick_count", 0)),
            "xlabel_count": int(get("xlabel_count", 12)),
            "max_ticks": int(get("max_ticks", 12)),
            "line_width": float(get("linewidth", 1.5)),
            "marker_size": float(get("markersize", 0)),
            "marker_edge_width": float(get("marker_edge", 2.5)),
            "series_styles": series_styles or None,
            "year_ruler": bool(get("year_ruler", False)),
            "grid": grid_on,
            "grid_axis": grid_axis,
            "grid_linewidth": grid_linewidth,
            "grid_linestyle": grid_linestyle,
            "show_legend": show_legend,
            "legend_loc": legend_location,
            "legend_labels": legend_labels,
            "legend_bbox": legend_bbox,
            "legend_size": legend_size,
            "legend_title": get("legend_title", "") or None,
            "legend_cols": int(get("legend_cols", 1)) or None,
            "title_loc": TITLE_POSITION_MAP.get(
                get("title_pos", "上居中"), ("center", "top")
            )[0],
            "title_pad": float(get("title_pad", 12.0)),
            "title_position": TITLE_POSITION_MAP.get(
                get("title_pos", "上居中"), ("center", "top")
            )[1],
            "xtitle_loc": XTITLE_LOCATION_MAP.get(
                get("xtitle_loc", "中"), "center"
            ),
            "ytitle_position": YTITLE_POSITION_MAP.get(
                get("ytitle_pos", "置顶"), "top"
            ),
            "note": note or None,
            "note_loc": NOTE_LOCATION_MAP.get(
                get("note_loc", "左"), "left"
            ),
            "note_prefix": get("note_prefix", "数据来源：") or None,
            "show_values": bool(get("show_values", False)),
            "value_decimals": int(get("value_decimals", 1)),
            "facet": bool(get("facet", False)),
            "facet_rows": int(get("facet_rows", 0)) or None,
            "facet_cols": int(get("facet_cols", 0)) or None,
            "figsize": (
                float(get("width", 12.8)),
                float(get("height", 7.2)),
            ),
            "sharex": bool(get("sharex", True)),
            "sharey": bool(get("sharey", False)),
            "auto_dual_y": bool(get("auto_dual_y", False)),
            "scale_ratio_threshold": float(
                get("scale_ratio_threshold", 10.0)
            ),
            "axis_groups": axis_groups,
            "max_y_axes": int(get("max_y_axes", 3)),
            "second_axis_vars": (
                list(get("second_axis", []) or [])
                if get("second_axis_on", False)
                and not get("auto_dual_y", False)
                else None
            ),
            "third_axis_vars": (
                list(get("third_axis", []) or [])
                if get("third_axis_on", False)
                and not get("auto_dual_y", False)
                else None
            ),
            "second_axis_title": (
                get("second_axis_title", "") or None
            ),
            "third_axis_title": (
                get("third_axis_title", "") or None
            ),
            "log_vars": list(get("log_vars", []) or []),
            "unit": get("unit", "") or None,
            "units": units,
            "colors": series_colors,
            "vlines": vlines,
            "hlines": hlines,
            "vline_color": COLOR_HEX_MAP.get(
                get("vline_color", "红"), "#d9534f"
            ),
            "vline_linestyle": get("vline_style", "--"),
            "vline_linewidth": float(get("vline_linewidth", 1.5)),
            "hline_color": COLOR_HEX_MAP.get(
                get("hline_color", "红"), "#d9534f"
            ),
            "hline_linestyle": get("hline_style", "--"),
            "hline_linewidth": float(get("hline_linewidth", 1.5)),
            "shade": shade,
            "shade_color": COLOR_HEX_MAP.get(
                get("shade_color", "灰"), "#999999"
            ),
            "shade_alpha": float(get("shade_alpha", 0.3)),
        },
        errors,
    )


__all__ = [
    "build_chart_options",
    "build_table_options",
    "preview_table_frame",
    "series_style_widget_key",
    "trim_to_valid_range",
]
