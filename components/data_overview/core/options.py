"""数据概览的选项构建层：会话状态 → 表格/绘图参数（纯函数）。

build_* 系列输入为状态映射（如 st.session_state），不直接依赖
streamlit，可脱离 UI 单测；输出与 Ts plot_series 签名一一对应
（由 tests/test_options.py 断言）。key_prefix 参数隔离不同实例
的 widget 键（默认 "sarimax" 与历史行为一致）。
"""

from __future__ import annotations

import pandas as pd

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
from .parsing import parse_float, parse_shade, parse_vlines, time_mask


def _get(state, key: str, default):
    value = state.get(key, default)
    return default if value is None else value


def build_table_options(state, dataset, *, key_prefix: str = "sarimax") -> dict:
    """从状态读取数据表高级选项的当前筛选与视图状态。

    预览表在 expander 之前渲染，控件值需经 session_state 读取；
    首次运行（控件尚未渲染）时回退到与控件默认值一致的默认参数。
    返回 dict：mask（布尔筛选掩码）、view（head/tail/all）。
    """

    def get(name: str, default):
        return _get(state, f"{key_prefix}_table_{name}", default)

    view_head = bool(get("view_head", True))
    view_tail = bool(get("view_tail", False))

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

    if view_tail:
        view = "tail"
    elif view_head:
        view = "head"
    else:
        view = "all"
    return {"mask": mask, "view": view}


def preview_table_frame(
    dataset,
    filtered,
    view: str,
    table_columns: list[str],
) -> pd.DataFrame:
    """构建预览表内容：按视图取头/尾/全部，时间列转字符串显示。

    时间列转为字符串显示（YYYY-MM-DD）：Streamlit 1.61 前端
    statistics 对 datetime 列存在微秒/纳秒单位换算 bug（min 会
    显示为错误年份），字符串列走文本统计，显示正确的最小日期。
    """
    if view == "tail":
        preview_frame = filtered.tail(PREVIEW_TABLE_ROWS)
    elif view == "all":
        preview_frame = filtered
    else:
        preview_frame = filtered.head(PREVIEW_TABLE_ROWS)
    preview_frame = preview_frame.loc[:, table_columns]
    if dataset.time_column is not None:
        preview_frame = preview_frame.copy()
        preview_frame[dataset.time_column] = preview_frame[
            dataset.time_column
        ].dt.strftime("%Y-%m-%d")
    return preview_frame


def build_chart_options(
    state,
    dataset,
    filtered,
    *,
    key_prefix: str = "sarimax",
) -> tuple[dict, list[str]]:
    """从状态读取图形高级选项控件的当前值，构建绘图参数。

    绘图在 expander 之前渲染，控件值需经 session_state 读取；
    首次运行（控件尚未渲染）时回退到与控件默认值一致的默认参数。
    filtered：当前筛选后的数据框（与绘图一致），参考线与阴影的
    行序号按它换算为 X 轴位置。
    返回 (绘图参数 dict, 解析错误列表)。输出键与 Ts plot_series
    参数一一对应（auto_dual_y 固定 False，由 UI 层调用时传入）。
    """

    def get(name: str, default):
        return _get(state, f"{key_prefix}_preview_{name}", default)

    # 三个标题（图/X/Y）均为常显输入框：填写才显示，留空不显示。
    # X 轴标题留空必须传 ""（而非 None）：None 会触发绘图层的
    # 兼容路径自动使用时间列名，违背"填写才显示"。
    title = get("title", "") or None
    note = get("note", "") or None
    xtitle = get("xtitle", "")
    ytitle = get("ytitle", "") or None

    # X 轴位置序列（按当前筛选后的数据计，与绘图一致）：
    # 参考线/阴影按行号或日期解析时都需要它。
    x_values = (
        filtered[dataset.time_column]
        if dataset.time_column is not None
        else filtered.index
    )

    vlines_text = get("vlines", "")
    shade_text = get("shade", "")
    vlines, vlines_error = parse_vlines(vlines_text, x_values)
    shade, shade_error = parse_shade(shade_text, x_values)
    errors = [error for error in (vlines_error, shade_error) if error]

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
            "line_width": float(get("linewidth", 1.5)),
            "marker_size": float(get("markersize", 0)),
            "marker_edge_width": float(get("marker_edge", 2.5)),
            "year_ruler": bool(get("year_ruler", False)),
            "grid": grid_on,
            "grid_axis": grid_axis,
            "grid_linewidth": grid_linewidth,
            "grid_linestyle": grid_linestyle,
            "show_legend": bool(get("legend", True)),
            "legend_loc": get("legend_loc", "best"),
            "legend_title": get("legend_title", "") or None,
            "legend_cols": int(get("legend_cols", 1)) or None,
            "title_loc": TITLE_POSITION_MAP.get(
                get("title_pos", "上居中"), ("center", "top")
            )[0],
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
            "sharey": bool(get("sharey", False)),
            "second_axis_vars": (
                list(get("second_axis", []) or [])
                if get("second_axis_on", False)
                else []
            ),
            "third_axis_vars": (
                list(get("third_axis", []) or [])
                if get("third_axis_on", False)
                else []
            ),
            "second_axis_title": (
                get("second_axis_title", "") or None
            ),
            "third_axis_title": (
                get("third_axis_title", "") or None
            ),
            "log_vars": list(get("log_vars", []) or []),
            "vlines": vlines,
            "vline_color": COLOR_HEX_MAP.get(
                get("vline_color", "红"), "#d9534f"
            ),
            "vline_linestyle": get("vline_style", "--"),
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
]
