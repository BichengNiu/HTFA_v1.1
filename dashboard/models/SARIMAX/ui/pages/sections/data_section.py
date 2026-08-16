"""SARIMAX 工作流 - ① 数据概览环节（共享数据集表格 + 时间序列预览图）。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
from Ts.TsPlots import plot_series

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.shared_dataset import (
    get_shared_dataset_data,
    get_shared_dataset_fingerprint,
    get_shared_dataset_name,
    get_shared_dataset_sheet,
    get_shared_dataset_sheets,
    render_shared_dataset_uploader,
    select_shared_dataset_sheet,
)
from dashboard.explore.analysis.stationarity import matplotlib_date_compatibility
from dashboard.models.SARIMAX.core.data_loader import (
    build_modeling_dataset,
    numeric_variable_names,
)
from dashboard.models.SARIMAX.ui.state import (
    WIDGET_KEYS,
    clear_fit_results,
    clear_widget_state,
    state,
)

logger = logging.getLogger(__name__)

# 预览图可调参数范围（与 TsPlots.plot_series 参数对应）。
_LINE_WIDTH_RANGE = (0.5, 4.0)
_MARKER_SIZE_RANGE = (0, 12)
_MARKER_EDGE_RANGE = (0.0, 4.0)
_LEGEND_LOCATIONS = (
    "best",
    "upper right",
    "upper left",
    "lower left",
    "lower right",
)
_TITLE_POSITIONS = ("左上", "上居中", "右上", "下居中")
_TITLE_POSITION_MAP = {
    "左上": ("left", "top"),
    "上居中": ("center", "top"),
    "右上": ("right", "top"),
    "下居中": ("center", "bottom"),
}
_XTITLE_LOCATIONS = ("左", "中", "右")
_XTITLE_LOCATION_MAP = {"左": "left", "中": "center", "右": "right"}
_NOTE_LOCATIONS = ("左", "中", "右")
_NOTE_LOCATION_MAP = {"左": "left", "中": "center", "右": "right"}
_YTITLE_POSITIONS = ("置顶", "侧边")
_YTITLE_POSITION_MAP = {"置顶": "top", "侧边": "side"}
_FREQUENCIES = ("自动", "day", "week", "month", "quarter", "year")
_REFERENCE_LINE_STYLES = ("--", "-", ":", "-.")
_GRID_STYLES = ("不显示", "纵网格", "横网格", "纵横网格")
_GRID_STYLE_MAP = {
    "不显示": (False, "both"),
    "纵网格": (True, "x"),
    "横网格": (True, "y"),
    "纵横网格": (True, "both"),
}
_GRID_LINESTYLES = ("--", "-", ":", "-.")
_GRID_WIDTH_RANGE = (0.2, 3.0)
_COLOR_NAMES = ("红", "橙", "黄", "绿", "蓝", "紫", "灰")
_COLOR_HEX_MAP = {
    "红": "#d9534f",
    "橙": "#e67e22",
    "黄": "#f1c40f",
    "绿": "#2ecc71",
    "蓝": "#3498db",
    "紫": "#9b59b6",
    "灰": "#999999",
}
_ASPECT_RATIOS = ("自定义", "16:9", "4:3", "3:2", "1:1")
_ASPECT_RATIO_MAP = {"16:9": 16 / 9, "4:3": 4 / 3, "3:2": 3 / 2, "1:1": 1.0}

# 数据表高级选项：数值筛选运算符（显示文本 -> pandas 比较方法）。
_FILTER_OPERATORS = {
    "≥": "ge",
    "≤": "le",
    ">": "gt",
    "<": "lt",
    "=": "eq",
}

# 时间筛选预设（按数据频率），value 为最近期数（"custom" 为自定义）。
_TIME_PRESETS = {
    "year": [
        ("全部", "all"),
        ("过去1年", "1"),
        ("过去3年", "3"),
        ("过去5年", "5"),
        ("自定义", "custom"),
    ],
    "quarter": [
        ("全部", "all"),
        ("过去1季度", "1"),
        ("过去2季度", "2"),
        ("过去4季度", "4"),
        ("自定义", "custom"),
    ],
    "month": [
        ("全部", "all"),
        ("过去1个月", "1"),
        ("过去3个月", "3"),
        ("过去6个月", "6"),
        ("过去12个月", "12"),
        ("自定义", "custom"),
    ],
    "week": [
        ("全部", "all"),
        ("过去1周", "1"),
        ("过去4周", "4"),
        ("过去12周", "12"),
        ("过去52周", "52"),
        ("自定义", "custom"),
    ],
    "day": [
        ("全部", "all"),
        ("过去7天", "7"),
        ("过去30天", "30"),
        ("过去90天", "90"),
        ("过去365天", "365"),
        ("自定义", "custom"),
    ],
}
# 频率 -> 自定义起止的 Period 频率（年/季/月；周与日走日期控件）。
_FREQ_PERIOD = {"year": "Y", "quarter": "Q", "month": "M"}

# 预览表格默认显示行数。
_PREVIEW_TABLE_ROWS = 10
# 图形纵横比 16:9 宽幅：点右上角放大（全屏展开）时图表能自适应整个
# 页面；dpi=200 保证放大后仍清晰。普通视图下图形在 5/9 图列内拉伸，
# 宽幅渲染高度与 10 行表格高度接近。
_PREVIEW_FIGSIZE = (12.8, 7.2)
_PREVIEW_DPI = 200


def render_data_overview_section(st_obj) -> None:
    """展示共享数据集并绘制所选变量的时间序列预览图。

    第一行：数据上传组件独占一行；
    第二行：工作表选择（左）与变量选择（右）并排；
    预览表与时间序列图都受「数据表高级选项」的筛选条件驱动。
    """
    st_obj.markdown("#### ① 数据概览")
    render_shared_dataset_uploader(st_obj, compact=True)

    data = get_shared_dataset_data()
    if data is None:
        st_obj.info("请在上方上传数据文件（CSV / XLSX / XLS）。")
        return

    fingerprint = get_shared_dataset_fingerprint()
    dataset = state.get("dataset")
    if dataset is None or dataset.fingerprint != fingerprint:
        try:
            dataset = build_modeling_dataset(
                data,
                get_shared_dataset_name(),
                fingerprint,
            )
        except Exception as exc:  # noqa: BLE001 - 用户可读的数据解析边界
            st_obj.error(f"数据集校验失败：{exc}")
            return
        state.set("dataset", dataset)
        state.set("target_variable", None)
        state.set("exog_variables", ())
        clear_fit_results()
        clear_widget_state(st_obj, WIDGET_KEYS[1:])

    variables = numeric_variable_names(dataset.frame)
    if not variables:
        st_obj.error("数据中没有可用的数值型变量。")
        return

    # 第二行：工作表选择（左）与变量选择（右）并排。工作表选择在
    # dataset 构建之后渲染，避免 clear_widget_state 清掉其选中状态。
    sheets = get_shared_dataset_sheets()
    if sheets and len(sheets) > 1:
        selection_columns = st_obj.columns(2, vertical_alignment="center")
        with selection_columns[0]:
            if (
                "sarimax_preview_sheet" in st.session_state
                and st.session_state["sarimax_preview_sheet"] not in sheets
            ):
                st.session_state["sarimax_preview_sheet"] = sheets[0]
            current_sheet = get_shared_dataset_sheet()
            st_obj.selectbox(
                "选择工作表",
                options=sheets,
                index=sheets.index(current_sheet)
                if current_sheet in sheets
                else 0,
                key="sarimax_preview_sheet",
                on_change=_on_sheet_change,
                help="Excel 文件包含多个工作表时，切换后重新加载该表数据。",
            )
        with selection_columns[1]:
            selected = _render_variable_selector(st_obj, variables)
    else:
        selected = _render_variable_selector(st_obj, variables)
    if not selected:
        st_obj.info("请至少选择一个变量。")
        return

    # 表与图左右分栏（表 4 : 图 5，使图渲染高度接近 10 行表格高度）；
    # 表格受数据表高级选项的筛选/视图控制，默认显示前 10 行，
    # 不设固定高度（避免多余空行）。
    table_state = _table_options_from_state(dataset)
    filtered = dataset.frame.loc[table_state["mask"]]
    overview_columns = st_obj.columns([4, 5])
    with overview_columns[0]:
        table_columns = list(selected)
        if dataset.time_column is not None:
            table_columns = [dataset.time_column, *table_columns]
        if table_state["view"] == "tail":
            preview_frame = filtered.tail(_PREVIEW_TABLE_ROWS)
        elif table_state["view"] == "all":
            preview_frame = filtered
        else:
            preview_frame = filtered.head(_PREVIEW_TABLE_ROWS)
        # 时间列转为字符串显示（YYYY-MM-DD）：Streamlit 1.61 前端
        # statistics 对 datetime 列存在微秒/纳秒单位换算 bug（min 会
        # 显示为错误年份），字符串列走文本统计，显示正确的最小日期。
        preview_frame = preview_frame.loc[:, table_columns]
        if dataset.time_column is not None:
            preview_frame = preview_frame.copy()
            preview_frame[dataset.time_column] = preview_frame[
                dataset.time_column
            ].dt.strftime("%Y-%m-%d")
        st_obj.dataframe(
            preview_frame,
            width="stretch",
        )
        _render_view_toggles(st_obj)
        st_obj.caption(
            f"当前筛选：{len(filtered):,} 行 / 共 {len(dataset.frame):,} 行"
        )
    with overview_columns[1]:
        if filtered.empty:
            st_obj.info("筛选结果为空，暂无数据可绘制。")
        else:
            options, errors = _preview_options_from_state(dataset, filtered)
            if errors:
                st_obj.warning("；".join(errors))
            _draw_series_plot(
                st_obj, dataset, selected, filtered=filtered, **options
            )

    # 表与图下方：数据表高级选项与图形高级选项左右并排。
    # 注意：函数内部必须用全局 st_obj（main DG）调用容器方法，
    # Streamlit 的 with 栈只对 main DG 生效（容器方法忽略 with 栈）。
    option_columns = st_obj.columns(2)
    with option_columns[0]:
        _render_table_options_expander(st_obj, dataset, selected)
    with option_columns[1]:
        _render_chart_options_expander(st_obj, dataset, selected)


def _draw_series_plot(
    st_obj,
    dataset,
    variables: list[str],
    *,
    title: str | None = None,
    xtitle: str | None = None,
    ytitle: str | None = None,
    ytitle_position: str = "top",
    xtitle_loc: str = "center",
    ymin: float | None = None,
    xmin=None,
    ytick_count: int | None = 0,
    ylabel_count: int | None = 5,
    xtick_count: int | None = 0,
    xlabel_count: int | None = 12,
    line_width: float = 1.5,
    marker_size: float = 0,
    marker_edge_width: float = 2.5,
    year_ruler: bool = False,
    grid: bool = True,
    grid_axis: str = "both",
    grid_linewidth: float = 0.6,
    grid_linestyle: str = "--",
    show_legend: bool = True,
    legend_loc: str = "best",
    legend_title: str | None = None,
    legend_cols: int | None = None,
    title_loc: str = "center",
    title_position: str = "top",
    note: str | None = None,
    note_loc: str = "left",
    note_prefix: str | None = None,
    show_values: bool = False,
    value_decimals: int = 1,
    facet: bool = False,
    facet_rows: int | None = None,
    facet_cols: int | None = None,
    figsize: tuple[float, float] | None = None,
    sharey: bool = False,
    second_axis_vars: list[str] | None = None,
    third_axis_vars: list[str] | None = None,
    second_axis_title: str | None = None,
    third_axis_title: str | None = None,
    log_vars: list[str] | None = None,
    vlines=None,
    vline_color: str = "#d9534f",
    vline_linestyle: str = "--",
    shade=None,
    shade_color: str = "#d0d0d0",
    shade_alpha: float = 0.3,
    filtered=None,
) -> None:
    """调用 TsPlots.plot_series 绘制所选变量，并渲染到页面。

    filtered：筛选后的数据框（与 dataset.frame 同结构）；传入时
    只绘制筛选范围内的序列，与上方预览表一致。
    """
    source = filtered if filtered is not None else dataset.frame
    if dataset.time_column is not None:
        plot_frame = source.set_index(dataset.time_column).loc[:, variables]
        default_xtitle = dataset.time_column
    else:
        plot_frame = source.loc[:, variables]
        default_xtitle = "观测序号"

    # xtitle："" 表示不显示 X 轴标签；None 表示自动使用时间列名
    # （当前 UI 不传 None——留空即不显示）。
    x_label = default_xtitle if xtitle is None else xtitle
    try:
        fig, ax = plot_series(
            plot_frame,
            title=title or None,
            xtitle=x_label,
            xtitle_loc=xtitle_loc,
            ytitle=ytitle,
            ytitle_position=ytitle_position,
            ymin=ymin,
            xmin=xmin,
            ytick_count=ytick_count,
            ylabel_count=ylabel_count,
            xtick_count=xtick_count,
            xlabel_count=xlabel_count,
            linewidth=line_width,
            markersize=marker_size,
            marker_edge_width=marker_edge_width,
            year_ruler=year_ruler,
            grid=grid,
            grid_axis=grid_axis,
            grid_linewidth=grid_linewidth,
            grid_linestyle=grid_linestyle,
            show_legend=show_legend,
            legend_loc=legend_loc,
            title_loc=title_loc,
            title_position=title_position,
            note=note,
            note_loc=note_loc,
            note_prefix=note_prefix,
            show_values=show_values,
            value_decimals=value_decimals,
            facet=facet,
            facet_rows=facet_rows,
            facet_cols=facet_cols,
            figsize=figsize,
            sharey=sharey,
            auto_dual_y=False,
            second_axis_vars=second_axis_vars,
            third_axis_vars=third_axis_vars,
            second_axis_title=second_axis_title,
            third_axis_title=third_axis_title,
            log_vars=log_vars,
            vlines=vlines,
            vline_color=vline_color,
            vline_linestyle=vline_linestyle,
            shade=shade,
            shade_color=shade_color,
            shade_alpha=shade_alpha,
        )
    except Exception:
        logger.exception("SARIMAX 时间序列预览绘图失败")
        raise

    fig.set_size_inches(_PREVIEW_FIGSIZE)
    fig.set_dpi(_PREVIEW_DPI)
    with matplotlib_date_compatibility():
        render_pyplot_figure(
            st_obj,
            fig,
            place_legend_bottom=(legend_loc == "best"),
            legend_title=legend_title,
            legend_cols=legend_cols,
        )


def _render_variable_selector(st_obj, variables: list[str]) -> list[str]:
    """变量筛选器（同时控制左侧数据表与右侧时间序列图）。"""
    return st_obj.multiselect(
        "选择变量",
        options=variables,
        default=[variables[0]],
        key="sarimax_preview_vars",
        help="选择一个或多个变量；数据表只显示选中列，时间序列图绘制选中序列。",
    )


def _render_view_toggles(st_obj) -> None:
    """预览表下方的视图开关（头10行 / 尾10行，互斥并排）。

    默认值经 session_state 预置，避免 checkbox 的 value 参数与
    互斥回调写入冲突。
    """
    for key, default in (
        ("sarimax_table_view_head", True),
        ("sarimax_table_view_tail", False),
    ):
        if key not in st.session_state:
            st.session_state[key] = default
    toggle_row = st_obj.columns(2)
    toggle_row[0].checkbox(
        "显示头10行",
        key="sarimax_table_view_head",
        on_change=_exclusive_view_callback("sarimax_table_view_head"),
        help="预览表显示筛选结果的前 10 行；取消勾选则显示全部。",
    )
    toggle_row[1].checkbox(
        "显示尾10行",
        key="sarimax_table_view_tail",
        on_change=_exclusive_view_callback("sarimax_table_view_tail"),
        help="预览表显示筛选结果的最后 10 行。",
    )


def _exclusive_view_callback(current_key: str):
    """互斥视图开关：勾选其中一个时取消另一个（head/tail）。"""

    def _callback() -> None:
        for key in (
            "sarimax_table_view_head",
            "sarimax_table_view_tail",
        ):
            if key != current_key:
                st.session_state[key] = False

    return _callback


def _on_sheet_change() -> None:
    """工作表切换回调：重载对应 sheet 的共享数据。"""
    sheet = st.session_state.get("sarimax_preview_sheet")
    if sheet:
        select_shared_dataset_sheet(sheet)


def _detect_frequency(dates) -> str:
    """按时间间隔中位数推断数据频率：year/quarter/month/week/day。"""
    series = pd.to_datetime(pd.Series(dates)).sort_values()
    if len(series) < 2:
        return "day"
    diffs = series.diff().dropna()
    if diffs.empty:
        return "day"
    median = diffs.median()
    if median >= pd.Timedelta(days=330):
        return "year"
    if median >= pd.Timedelta(days=85):
        return "quarter"
    if median >= pd.Timedelta(days=25):
        return "month"
    if median >= pd.Timedelta(days=5):
        return "week"
    return "day"


def _period_bounds(text: str, freq: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """把按频率粒度的选择文本转换为 (起始, 结束) 时间戳。"""
    if freq in ("day", "week"):
        ts = pd.Timestamp(text)
        return ts, ts
    period = pd.Period(text, _FREQ_PERIOD[freq])
    return period.start_time, period.end_time


def _time_mask(dataset, ss) -> pd.Series:
    """按时间筛选预设/自定义起止构造布尔掩码（频率匹配数据粒度）。"""
    time_series = pd.to_datetime(dataset.frame[dataset.time_column])
    mask = pd.Series(True, index=dataset.frame.index)
    freq = _detect_frequency(time_series)
    preset_label = ss.get("sarimax_table_time_preset")
    if preset_label is None:
        return mask
    preset_value = dict(_TIME_PRESETS[freq]).get(preset_label, "all")
    if preset_value == "all":
        return mask
    last = time_series.max()
    if preset_value == "custom":
        start = ss.get("sarimax_table_time_start")
        end = ss.get("sarimax_table_time_end")
        if start is None or end is None:
            return mask
        start_ts, _ = _period_bounds(str(start), freq)
        _, end_ts = _period_bounds(str(end), freq)
    else:
        # 按数据实际点位取最近 N 期（如月度数据「过去3个月」= 最后 3 个
        # 数据点），与数据频率和实际范围精确匹配。
        periods = int(preset_value)
        sorted_dates = time_series.sort_values().unique()
        if len(sorted_dates) <= periods:
            return mask
        start_ts = pd.Timestamp(sorted_dates[-periods])
        end_ts = last
    return mask & (time_series >= start_ts) & (time_series <= end_ts)


def _render_time_filter(st_obj, dataset) -> None:
    """按数据频率渲染时间筛选：预设快捷范围 + 自定义起止（粒度匹配）。"""
    time_series = pd.to_datetime(dataset.frame[dataset.time_column])
    freq = _detect_frequency(time_series)
    presets = _TIME_PRESETS[freq]
    labels = [label for label, _ in presets]
    st_obj.selectbox(
        "时间范围",
        options=labels,
        key="sarimax_table_time_preset",
        help=(
            f"数据为{freq}频率；快捷范围按最近期数计算，"
            f"自定义范围只能选择到{freq}粒度，且限定在数据范围内。"
        ),
    )
    preset_label = st.session_state.get("sarimax_table_time_preset")
    if preset_label != "自定义":
        st.session_state.pop("sarimax_table_time_start", None)
        st.session_state.pop("sarimax_table_time_end", None)
        return

    if freq == "year":
        years = sorted(time_series.dt.year.unique().astype(str))
        row = st_obj.columns(2)
        row[0].selectbox("起始年", options=years, key="sarimax_table_time_start")
        row[1].selectbox(
            "结束年", options=years, index=len(years) - 1, key="sarimax_table_time_end"
        )
    elif freq == "quarter":
        quarters = sorted(time_series.dt.to_period("Q").astype(str).unique())
        row = st_obj.columns(2)
        row[0].selectbox(
            "起始季度", options=quarters, key="sarimax_table_time_start"
        )
        row[1].selectbox(
            "结束季度",
            options=quarters,
            index=len(quarters) - 1,
            key="sarimax_table_time_end",
        )
    elif freq == "month":
        months = sorted(time_series.dt.strftime("%Y-%m").unique())
        row = st_obj.columns(2)
        row[0].selectbox("起始年月", options=months, key="sarimax_table_time_start")
        row[1].selectbox(
            "结束年月",
            options=months,
            index=len(months) - 1,
            key="sarimax_table_time_end",
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
            key="sarimax_table_time_start",
        )
        row[1].date_input(
            "结束日期",
            value=date_max,
            min_value=date_min,
            max_value=date_max,
            key="sarimax_table_time_end",
        )


def _table_options_from_state(dataset) -> dict:
    """从 session_state 读取数据表高级选项的当前筛选与视图状态。

    预览表在 expander 之前渲染，控件值需经 session_state 读取；
    首次运行（控件尚未渲染）时回退到与控件默认值一致的默认参数。
    返回 dict：mask（布尔筛选掩码）、view（head/tail/all）。
    """
    ss = st.session_state

    def get(key: str, default):
        value = ss.get(key, default)
        return default if value is None else value

    view_head = bool(get("sarimax_table_view_head", True))
    view_tail = bool(get("sarimax_table_view_tail", False))

    frame = dataset.frame
    mask = pd.Series(True, index=frame.index)
    filter_col = get("sarimax_table_filter_col", "无")
    filter_op = get("sarimax_table_filter_op", "≥")
    filter_val = float(get("sarimax_table_filter_val", 0.0))
    if filter_col != "无":
        mask &= getattr(frame[filter_col], _FILTER_OPERATORS[filter_op])(
            filter_val
        )
    if dataset.time_column is not None:
        mask &= _time_mask(dataset, ss)

    if view_tail:
        view = "tail"
    elif view_head:
        view = "head"
    else:
        view = "all"
    return {"mask": mask, "view": view}


def _render_table_options_expander(st_obj, dataset, selected: list[str]) -> None:
    """数据表高级选项：筛选条件与统计量。

    视图开关（头10行/尾10行）已移到预览表下方并排展示；筛选条件经
    session_state 直接作用于上方的预览表（expander 内不再重复展示
    结果表），这里只渲染控件与统计量表。
    """
    frame = dataset.frame
    with st_obj.expander("数据表高级选项", expanded=False):
        # 筛选条件。
        row = st_obj.columns(3)
        row[0].selectbox(
            "筛选列",
            options=["无"] + list(selected),
            key="sarimax_table_filter_col",
            help="选择要按数值条件筛选的列；选择“无”表示不筛选。",
        )
        row[1].selectbox(
            "条件",
            options=list(_FILTER_OPERATORS),
            index=0,
            key="sarimax_table_filter_op",
        )
        row[2].number_input(
            "阈值",
            value=0.0,
            key="sarimax_table_filter_val",
        )

        if dataset.time_column is not None:
            _render_time_filter(st_obj, dataset)

        # 当前筛选掩码（与上方预览表一致），用于统计量。
        table_state = _table_options_from_state(dataset)
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


def _render_chart_options_expander(st_obj, dataset, selected) -> None:
    """表与图下方占一整行的图形高级选项（按逻辑分 tab 组织）。

    每个 tab 的第一行放全部开关（checkbox），第二排起放下拉菜单与
    输入控件；开关控制的条件输入仅在勾选后显示。
    """
    with st_obj.expander("图形高级选项", expanded=False):
        tab_canvas, tab_title, tab_axis, tab_lines, tab_legend = st_obj.tabs(
            [
                "画布",
                "标题",
                "坐标轴",
                "线条样式",
                "图例与图注",
            ]
        )

        with tab_canvas:
            # 第一行：尺寸——纵横比 / 宽度 / 高度（非自定义时高度跟随宽度）。
            size_row = tab_canvas.columns(3)
            aspect = size_row[0].selectbox(
                "纵横比",
                options=list(_ASPECT_RATIOS),
                index=1,
                key="sarimax_preview_aspect",
                help="16:9 为默认图比例；选自定义后可单独调宽高。",
            )
            size_row[1].number_input(
                "宽度",
                min_value=4.0,
                max_value=30.0,
                value=12.8,
                step=0.1,
                key="sarimax_preview_width",
                help="图宽度（英寸）。",
            )
            if aspect != "自定义":
                st_obj.session_state["sarimax_preview_height"] = round(
                    float(st_obj.session_state.get("sarimax_preview_width", 12.8))
                    / _ASPECT_RATIO_MAP[aspect],
                    1,
                )
            elif "sarimax_preview_height" not in st_obj.session_state:
                st_obj.session_state["sarimax_preview_height"] = 7.2
            size_row[2].number_input(
                "高度",
                min_value=3.0,
                max_value=20.0,
                step=0.1,
                key="sarimax_preview_height",
                help="图高度（英寸）；选择纵横比后自动跟随宽度。",
            )

            # 第二行：分面——开关 / 行数 / 列数（勾选后显示行列）。
            facet_row = tab_canvas.columns(3)
            facet_on = facet_row[0].checkbox(
                "分面显示",
                value=False,
                key="sarimax_preview_facet",
                help="多变量时每个变量一张子图；关闭则叠画在同一坐标区。",
            )
            if facet_on:
                facet_row[1].number_input(
                    "分面行数",
                    min_value=0,
                    max_value=10,
                    value=0,
                    step=1,
                    key="sarimax_preview_facet_rows",
                    help="0 表示自动；行数与列数至少一个为 0。",
                )
                facet_row[2].number_input(
                    "分面列数",
                    min_value=0,
                    max_value=10,
                    value=0,
                    step=1,
                    key="sarimax_preview_facet_cols",
                    help="0 表示自动。",
                )
            else:
                st_obj.session_state.pop("sarimax_preview_facet_rows", None)
                st_obj.session_state.pop("sarimax_preview_facet_cols", None)

        with tab_title:
            # 第一行：图标题内容 / 标题位置。
            title_row = tab_title.columns(2)
            title_row[0].text_input(
                "图标题内容",
                value="",
                key="sarimax_preview_title",
                help="填写后显示在图中；留空不显示。",
            )
            title_row[1].selectbox(
                "标题位置",
                options=list(_TITLE_POSITIONS),
                index=1,
                key="sarimax_preview_title_pos",
                help="图标题位置：左上 / 上居中 / 右上 / 下居中。",
            )

            # 第二行：X 轴标题内容 / X 轴标题位置。
            x_title_row = tab_title.columns(2)
            x_title_row[0].text_input(
                "X 轴标题内容",
                value="",
                key="sarimax_preview_xtitle",
                help="填写后显示；留空不显示。",
            )
            x_title_row[1].selectbox(
                "X 轴标题位置",
                options=list(_XTITLE_LOCATIONS),
                index=1,
                key="sarimax_preview_xtitle_loc",
                help="X 轴标题水平对齐：左 / 中 / 右。",
            )

            # 第三行：Y 轴标题内容 / Y 轴标题位置。
            y_title_row = tab_title.columns(2)
            y_title_row[0].text_input(
                "Y 轴标题内容",
                value="",
                key="sarimax_preview_ytitle",
                help="填写后显示；留空不显示。",
            )
            y_title_row[1].selectbox(
                "Y 轴标题位置",
                options=list(_YTITLE_POSITIONS),
                index=0,
                key="sarimax_preview_ytitle_pos",
                help="置顶横排（丁字：竖是轴、横是标题）；侧边为传统竖排在轴侧。",
            )

            # 第四行（联动）：第二/第三纵轴标题——在「坐标轴」tab 勾选
            # 了对应纵轴才弹出（控件渲染晚于读取，取上一次 session_state）。
            second_axis_on = bool(
                st_obj.session_state.get("sarimax_preview_second_axis_on", False)
            )
            third_axis_on = bool(
                st_obj.session_state.get("sarimax_preview_third_axis_on", False)
            )
            if second_axis_on or third_axis_on:
                axis_title_row = tab_title.columns(
                    2 if (second_axis_on and third_axis_on) else 1
                )
                column_index = 0
                if second_axis_on:
                    axis_title_row[column_index].text_input(
                        "第二纵轴标题",
                        value="",
                        key="sarimax_preview_second_axis_title",
                        help="第二纵轴（右侧内层）的标题；留空自动用变量名。",
                    )
                    column_index += 1
                if third_axis_on:
                    axis_title_row[column_index].text_input(
                        "第三纵轴标题",
                        value="",
                        key="sarimax_preview_third_axis_title",
                        help="第三纵轴（最外层）的标题；留空自动用变量名。",
                    )

        with tab_axis:
            # 第一行：轴开关排——年份标尺 / 第二纵轴 / 第三纵轴 / 分面共享 Y 轴。
            toggle_row = tab_axis.columns(4)
            toggle_row[0].checkbox(
                "年份标尺",
                value=False,
                key="sarimax_preview_year_ruler",
                help="绘制严格月刻度并在 X 轴下方标注年份标尺（月度数据）。",
            )
            second_axis_on = toggle_row[1].checkbox(
                "第二纵轴",
                value=False,
                key="sarimax_preview_second_axis_on",
                help="勾选后在底部显示「第二纵轴变量」选择栏。",
            )
            third_axis_on = toggle_row[2].checkbox(
                "第三纵轴",
                value=False,
                key="sarimax_preview_third_axis_on",
                help="勾选后在底部显示「第三纵轴变量」选择栏。",
            )
            toggle_row[3].checkbox(
                "分面共享 Y 轴",
                value=False,
                key="sarimax_preview_sharey",
                help="分面开启时各子图共享同一 Y 轴刻度范围。",
            )

            # 第二行：Y 轴相关——起点 / 标签数 / 刻度数 / 对数尺度。
            y_row = tab_axis.columns(4)
            y_row[0].text_input(
                "Y 轴起点",
                value="",
                key="sarimax_preview_ymin",
                help="留空自动；只支持固定起点，终点始终自动。",
            )
            y_row[1].number_input(
                "Y 轴标签数",
                min_value=1,
                max_value=40,
                value=5,
                step=1,
                key="sarimax_preview_ylabel_count",
                help="Y 轴最多显示的刻度标签数（刻度保留、标签均匀抽稀）。",
            )
            y_row[2].number_input(
                "Y 轴刻度数",
                min_value=0,
                max_value=20,
                value=0,
                step=1,
                key="sarimax_preview_ytick_count",
                help="每两个标签之间显示的子刻度线数；0 表示不显示。",
            )
            y_row[3].multiselect(
                "Y 轴对数尺度",
                options=selected,
                key="sarimax_preview_log_vars",
                help="选中变量的所在轴使用对数尺度；留空全部线性。",
            )

            # 第三行：时间轴相关——起点 / 标签数 / 刻度数。
            x_row = tab_axis.columns(3)
            x_row[0].text_input(
                "X 轴起点",
                value="",
                key="sarimax_preview_xmin",
                help="时间轴填日期（如 2020-04-01），数值轴填数字；留空自动。",
            )
            x_row[1].number_input(
                "X 轴标签数",
                min_value=1,
                max_value=40,
                value=12,
                step=1,
                key="sarimax_preview_xlabel_count",
                help="X 轴最多显示的刻度标签数（刻度保留、标签均匀抽稀）。",
            )
            x_row[2].number_input(
                "X 轴刻度数",
                min_value=0,
                max_value=20,
                value=0,
                step=1,
                key="sarimax_preview_xtick_count",
                help="每两个标签之间显示的子刻度线数；0 表示不显示。",
            )

            # 第四行（条件）：勾选「第二纵轴 / 第三纵轴」后显示变量选择栏。
            if second_axis_on or third_axis_on:
                axis_vars_row = tab_axis.columns(
                    2 if (second_axis_on and third_axis_on) else 1
                )
                column_index = 0
                if second_axis_on:
                    axis_vars_row[column_index].multiselect(
                        "第二纵轴变量",
                        options=selected,
                        key="sarimax_preview_second_axis",
                        help="选中变量画在右侧内层第二纵轴；留空不画。",
                    )
                    column_index += 1
                if third_axis_on:
                    axis_vars_row[column_index].multiselect(
                        "第三纵轴变量",
                        options=selected,
                        key="sarimax_preview_third_axis",
                        help="选中变量画在最外层第三纵轴；留空不画。",
                    )
            else:
                st_obj.session_state.pop("sarimax_preview_second_axis", None)
                st_obj.session_state.pop("sarimax_preview_third_axis", None)

        with tab_lines:
            # 第一行：网格设置——样式 / 线粗度 / 线型（样式=不显示时其余隐藏）。
            grid_row = tab_lines.columns(3)
            grid_style = grid_row[0].selectbox(
                "网格样式",
                options=list(_GRID_STYLES),
                index=3,
                key="sarimax_preview_grid_style",
                help="纵网格=竖直网格线；横网格=水平网格线；纵横网格=两者。",
            )
            if grid_style != "不显示":
                grid_row[1].slider(
                    "网格线粗度",
                    min_value=_GRID_WIDTH_RANGE[0],
                    max_value=_GRID_WIDTH_RANGE[1],
                    value=0.6,
                    step=0.1,
                    key="sarimax_preview_grid_width",
                    help="网格线的粗细（点数）。",
                )
                grid_row[2].selectbox(
                    "网格线样式",
                    options=list(_GRID_LINESTYLES),
                    index=0,
                    key="sarimax_preview_grid_linestyle",
                )
            else:
                st_obj.session_state.pop("sarimax_preview_grid_width", None)
                st_obj.session_state.pop("sarimax_preview_grid_linestyle", None)

            # 第二行：线宽 / 标记大小 / 标记描边宽度（三个滑轴一行）。
            row = tab_lines.columns(3)
            row[0].slider(
                "线宽",
                min_value=_LINE_WIDTH_RANGE[0],
                max_value=_LINE_WIDTH_RANGE[1],
                value=1.5,
                step=0.5,
                key="sarimax_preview_linewidth",
            )
            row[1].slider(
                "标记大小",
                min_value=_MARKER_SIZE_RANGE[0],
                max_value=_MARKER_SIZE_RANGE[1],
                value=0,
                step=1,
                key="sarimax_preview_markersize",
                help="0 表示不显示标记。",
            )
            row[2].slider(
                "标记描边宽度",
                min_value=_MARKER_EDGE_RANGE[0],
                max_value=_MARKER_EDGE_RANGE[1],
                value=2.5,
                step=0.5,
                key="sarimax_preview_marker_edge",
            )

        with tab_legend:
            # 第一行：图例 / 标注开关 / 数值小数位（勾选标注时显示）。
            toggle_row = tab_legend.columns(3)
            toggle_row[0].checkbox(
                "显示图例",
                value=True,
                key="sarimax_preview_legend",
            )
            show_values = toggle_row[1].checkbox(
                "标注数据值",
                value=False,
                key="sarimax_preview_show_values",
                help="在每个数据点旁标注数值。",
            )
            if show_values:
                toggle_row[2].number_input(
                    "数值小数位",
                    min_value=0,
                    max_value=6,
                    value=1,
                    step=1,
                    key="sarimax_preview_value_decimals",
                )
            else:
                st.session_state.pop("sarimax_preview_value_decimals", None)

            # 第二行：图例位置 / 图例标题 / 图例列数。
            row = tab_legend.columns(3)
            row[0].selectbox(
                "图例位置",
                options=list(_LEGEND_LOCATIONS),
                index=0,
                key="sarimax_preview_legend_loc",
                help=(
                    "默认（best）图例置底；选择其他位置后"
                    "按所选位置显示。"
                ),
            )
            row[1].text_input(
                "图例标题",
                value="",
                key="sarimax_preview_legend_title",
                help="图例上方的小标题（如：变量）；留空不显示。",
            )
            row[2].number_input(
                "图例列数",
                min_value=1,
                max_value=8,
                value=1,
                step=1,
                key="sarimax_preview_legend_cols",
                help="图例条目排成几列；1 表示单列。",
            )

            # 第三行：图注设置——内容（最左）/ 位置 / 自动前缀。
            note_row = tab_legend.columns(3)
            note_row[0].text_input(
                "图注内容",
                value="",
                key="sarimax_preview_note",
                help="填写后显示在图中下方；留空不显示。",
            )
            note_row[1].selectbox(
                "图注位置",
                options=list(_NOTE_LOCATIONS),
                index=0,
                key="sarimax_preview_note_loc",
                help="图注在图中下方的水平位置：左 / 中 / 右。",
            )
            note_row[2].text_input(
                "自动前缀",
                value="数据来源：",
                key="sarimax_preview_note_prefix",
                help="自动加在图注内容前的文字；留空不显示前缀。",
            )

            # 第四行：参考线设置（留空即不显示）。
            row = tab_legend.columns(3)
            row[0].text_input(
                "垂直参考线",
                value="",
                key="sarimax_preview_vlines",
                help="逗号分隔：行号或日期，如 0,3,7 或 1987-07,1989-06；"
                "日期取第一个不早于该日期的数据点；行号按当前筛选后的数据计；"
                "留空不显示。",
            )
            row[1].selectbox(
                "参考线颜色",
                options=list(_COLOR_NAMES),
                index=0,
                key="sarimax_preview_vline_color",
            )
            row[2].selectbox(
                "参考线样式",
                options=list(_REFERENCE_LINE_STYLES),
                index=1,
                key="sarimax_preview_vline_style",
            )

            # 第五行：阴影设置（区间留空即不显示）。
            row = tab_legend.columns(3)
            row[0].text_input(
                "阴影区间",
                value="",
                key="sarimax_preview_shade",
                help="两两一组（起,止），逗号分隔，如 1987-07,1989-06 或"
                " 2,10,20,30（行号）；日期取第一个不早于该日期的数据点；"
                "留空不显示。",
            )
            row[1].selectbox(
                "阴影颜色",
                options=list(_COLOR_NAMES),
                index=6,
                key="sarimax_preview_shade_color",
            )
            row[2].slider(
                "阴影透明度",
                min_value=0.0,
                max_value=1.0,
                value=0.3,
                step=0.1,
                key="sarimax_preview_shade_alpha",
            )


def _preview_options_from_state(dataset, filtered) -> tuple[dict, list[str]]:
    """从 session_state 读取图形高级选项控件的当前值。

    绘图在 expander 之前渲染，控件值需经 session_state 读取；
    首次运行（控件尚未渲染）时回退到与控件默认值一致的默认参数。
    filtered：当前筛选后的数据框（与绘图一致），参考线与阴影的
    行序号按它换算为 X 轴位置。
    返回 (绘图参数 dict, 解析错误列表)。
    """
    ss = st.session_state

    def get(key: str, default):
        value = ss.get(key, default)
        return default if value is None else value

    # 三个标题（图/X/Y）均为常显输入框：填写才显示，留空不显示。
    # X 轴标题留空必须传 ""（而非 None）：None 会触发 _draw_series_plot
    # 的兼容路径自动使用时间列名，违背"填写才显示"。
    title = get("sarimax_preview_title", "") or None
    note = get("sarimax_preview_note", "") or None
    xtitle = get("sarimax_preview_xtitle", "")
    ytitle = get("sarimax_preview_ytitle", "") or None

    # X 轴位置序列（按当前筛选后的数据计，与绘图一致）：
    # 参考线/阴影按行号或日期解析时都需要它。
    x_values = (
        filtered[dataset.time_column]
        if dataset.time_column is not None
        else filtered.index
    )

    vlines_text = get("sarimax_preview_vlines", "")
    shade_text = get("sarimax_preview_shade", "")
    vlines, vlines_error = _parse_vlines(vlines_text, x_values)
    shade, shade_error = _parse_shade(shade_text, x_values)
    errors = [error for error in (vlines_error, shade_error) if error]

    # X 轴起点：时间轴解析为日期（Timestamp），数值轴解析为数字。
    xmin_text = get("sarimax_preview_xmin", "").strip()
    if xmin_text:
        if dataset.time_column is not None:
            try:
                xmin_value = pd.to_datetime(xmin_text)
            except (ValueError, TypeError):
                xmin_value = None
                errors.append(f"X 轴起点无法解析为日期：{xmin_text}")
        else:
            xmin_value = _parse_float(xmin_text)
            if xmin_value is None:
                errors.append(f"X 轴起点无法解析为数字：{xmin_text}")
    else:
        xmin_value = None

    grid_on, grid_axis = _GRID_STYLE_MAP.get(
        get("sarimax_preview_grid_style", "纵横网格"), (True, "both")
    )
    grid_linewidth = float(get("sarimax_preview_grid_width", 0.6))
    grid_linestyle = get("sarimax_preview_grid_linestyle", "--")

    return (
        {
            "title": title or None,
            "xtitle": xtitle,
            "ytitle": ytitle,
            "ymin": _parse_float(get("sarimax_preview_ymin", "")),
            "xmin": xmin_value,
            "ytick_count": int(get("sarimax_preview_ytick_count", 0)),
            "ylabel_count": int(get("sarimax_preview_ylabel_count", 5)),
            "xtick_count": int(get("sarimax_preview_xtick_count", 0)),
            "xlabel_count": int(get("sarimax_preview_xlabel_count", 12)),
            "line_width": float(get("sarimax_preview_linewidth", 1.5)),
            "marker_size": float(get("sarimax_preview_markersize", 0)),
            "marker_edge_width": float(get("sarimax_preview_marker_edge", 2.5)),
            "year_ruler": bool(get("sarimax_preview_year_ruler", False)),
            "grid": grid_on,
            "grid_axis": grid_axis,
            "grid_linewidth": grid_linewidth,
            "grid_linestyle": grid_linestyle,
            "show_legend": bool(get("sarimax_preview_legend", True)),
            "legend_loc": get("sarimax_preview_legend_loc", "best"),
            "legend_title": get("sarimax_preview_legend_title", "") or None,
            "legend_cols": int(get("sarimax_preview_legend_cols", 1)) or None,
            "title_loc": _TITLE_POSITION_MAP.get(
                get("sarimax_preview_title_pos", "上居中"), ("center", "top")
            )[0],
            "title_position": _TITLE_POSITION_MAP.get(
                get("sarimax_preview_title_pos", "上居中"), ("center", "top")
            )[1],
            "xtitle_loc": _XTITLE_LOCATION_MAP.get(
                get("sarimax_preview_xtitle_loc", "中"), "center"
            ),
            "ytitle_position": _YTITLE_POSITION_MAP.get(
                get("sarimax_preview_ytitle_pos", "置顶"), "top"
            ),
            "note": note or None,
            "note_loc": _NOTE_LOCATION_MAP.get(
                get("sarimax_preview_note_loc", "左"), "left"
            ),
            "note_prefix": get("sarimax_preview_note_prefix", "数据来源：")
            or None,
            "show_values": bool(get("sarimax_preview_show_values", False)),
            "value_decimals": int(get("sarimax_preview_value_decimals", 1)),
            "facet": bool(get("sarimax_preview_facet", False)),
            "facet_rows": int(get("sarimax_preview_facet_rows", 0)) or None,
            "facet_cols": int(get("sarimax_preview_facet_cols", 0)) or None,
            "figsize": (
                float(get("sarimax_preview_width", 12.8)),
                float(get("sarimax_preview_height", 7.2)),
            ),
            "sharey": bool(get("sarimax_preview_sharey", False)),
            "second_axis_vars": (
                list(get("sarimax_preview_second_axis", []) or [])
                if get("sarimax_preview_second_axis_on", False)
                else []
            ),
            "third_axis_vars": (
                list(get("sarimax_preview_third_axis", []) or [])
                if get("sarimax_preview_third_axis_on", False)
                else []
            ),
            "second_axis_title": (
                get("sarimax_preview_second_axis_title", "") or None
            ),
            "third_axis_title": (
                get("sarimax_preview_third_axis_title", "") or None
            ),
            "log_vars": list(get("sarimax_preview_log_vars", []) or []),
            "vlines": vlines,
            "vline_color": _COLOR_HEX_MAP.get(
                get("sarimax_preview_vline_color", "红"), "#d9534f"
            ),
            "vline_linestyle": get("sarimax_preview_vline_style", "--"),
            "shade": shade,
            "shade_color": _COLOR_HEX_MAP.get(
                get("sarimax_preview_shade_color", "灰"), "#999999"
            ),
            "shade_alpha": float(get("sarimax_preview_shade_alpha", 0.3)),
        },
        errors,
    )


def _parse_float(text: str) -> float | None:
    """解析可空的数值输入；空或非法时返回 None。"""
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_vlines(text: str, x_values) -> tuple[list | None, str | None]:
    """解析垂直参考线：逗号分隔，每项为行号或日期（如 1987-07）。"""
    text = text.strip()
    if not text:
        return None, None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return None, None
    resolved = []
    for part in parts:
        position, error = _resolve_position(part, x_values, "参考线")
        if error:
            return None, error
        resolved.append(position)
    return resolved, None


def _parse_shade(text: str, x_values) -> tuple[list[tuple] | None, str | None]:
    """解析阴影区间：逗号分隔两两一组（起,止,起,止…），行为行号或日期。"""
    text = text.strip()
    if not text:
        return None, None
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        return None, None
    if len(parts) % 2:
        return None, f"阴影区间应为两两一组（起,止）：{parts[-1]}"
    intervals = []
    for i in range(0, len(parts), 2):
        start, error = _resolve_position(parts[i], x_values, "阴影起点")
        if error:
            return None, error
        end, error = _resolve_position(parts[i + 1], x_values, "阴影终点")
        if error:
            return None, error
        if start > end:
            return None, f"阴影区间起点不能大于终点：{parts[i]}, {parts[i + 1]}"
        intervals.append((start, end))
    return intervals or None, None


def _resolve_position(text: str, x_values, label: str):
    """把输入解析为 X 轴位置：纯数字=行号；否则按日期解析（取第一个
    不早于该日期的数据点）。返回 (位置, 错误)；出错时位置为 None。"""
    text = text.strip()
    if text.isdigit():
        index = int(text)
        count = len(x_values)
        if index >= count:
            return None, f"{label}行号超出数据范围（0~{count - 1}）：{index}"
        value = x_values.iloc[index] if hasattr(x_values, "iloc") else x_values[index]
        return value, None

    if not pd.api.types.is_datetime64_any_dtype(x_values):
        return None, f"{label}无法解析（数据时间列不是日期类型，请填写行号）：{text}"
    try:
        target = pd.to_datetime(text)
    except (ValueError, TypeError):
        return None, f"{label}无法解析（应为行号或日期，如 1987-07）：{text}"
    if target < pd.Timestamp(x_values.iloc[0]):
        return None, f"{label}日期早于数据起点：{text}"
    candidates = x_values[x_values >= target]
    if not len(candidates):
        return None, f"{label}日期晚于数据终点：{text}"
    return candidates.iloc[0], None


__all__ = ["render_data_overview_section"]
