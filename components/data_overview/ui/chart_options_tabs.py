"""图形高级选项 5-tab 控件（画布 / 标题 / 坐标轴 / 线条样式 / 图例与图注）。

只负责渲染控件并写入 session_state；绘图参数由
core.overview.options.build_chart_options 读取（与 Ts plot_series
签名一一对应）。
"""

from __future__ import annotations

import streamlit as st
from Ts.TsPlots.style import DEFAULT_MARKERS, DEFAULT_PALETTE

from ..core.constants import (
    ASPECT_RATIO_MAP,
    ASPECT_RATIOS,
    COLOR_NAMES,
    GRID_LINESTYLES,
    GRID_STYLES,
    GRID_WIDTH_RANGE,
    LEGEND_LOCATIONS,
    LINE_WIDTH_RANGE,
    MARKER_EDGE_RANGE,
    MARKER_SIZE_RANGE,
    NOTE_LOCATIONS,
    REFERENCE_LINE_STYLES,
    SERIES_LINESTYLES,
    SERIES_MARKER_LABELS,
    SERIES_MARKERS,
    TITLE_POSITIONS,
    XTITLE_LOCATIONS,
    YTITLE_POSITIONS,
)
from ..core.options import series_style_widget_key
from .widget_keys import preview_key


_SERIES_COLOR_LABELS = (
    "黑",
    "深蓝",
    "灰",
    "深红",
    "中钢蓝",
    "银灰",
    "铜棕",
    "琥珀棕",
)
_SERIES_COLOR_SWATCHES = ("⬛", "🟦", "⬜", "🟥", "🔷", "▫️", "🟫", "🟨")


def _format_series_color(color: str) -> str:
    try:
        index = DEFAULT_PALETTE.index(color)
    except ValueError:
        return "■ 自定义"
    return f"{_SERIES_COLOR_SWATCHES[index]} {_SERIES_COLOR_LABELS[index]}"


def render_chart_options_expander(
    st_obj, selected, *, key_prefix: str = "sarimax"
) -> None:
    """表与图下方占一整行的图形高级选项（按逻辑分 tab 组织）。

    每个 tab 的第一行放全部开关（checkbox），第二排起放下拉菜单与
    输入控件；开关控制的条件输入仅在勾选后显示。
    """
    _k = lambda name: preview_key(key_prefix, name)  # noqa: E731
    with st_obj.expander(
        "图形高级选项",
        expanded=False,
        key=_k("chart_options_expander"),
        on_change="rerun",
    ):
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
            # 第一行：分面开关。
            facet_toggle = tab_canvas.columns(4)
            facet_on = facet_toggle[0].checkbox(
                "分面显示",
                value=False,
                key=_k("facet"),
                help=(
                    "多变量时在页面中为每个变量生成一张独立图；"
                    "关闭则叠画在同一图中。页面级分面不共享坐标轴。"
                ),
            )

            # 第二行：尺寸——纵横比 / 宽度 / 高度（非自定义时高度跟随宽度）。
            size_row = tab_canvas.columns(3)
            aspect = size_row[0].selectbox(
                "纵横比",
                options=list(ASPECT_RATIOS),
                index=1,
                key=_k("aspect"),
                help="16:9 为默认图比例；选自定义后可单独调宽高。",
            )
            size_row[1].number_input(
                "宽度",
                min_value=4.0,
                max_value=30.0,
                value=12.8,
                step=0.1,
                key=_k("width"),
                help="图宽度（英寸）。",
            )
            if aspect != "自定义":
                st_obj.session_state[_k("height")] = round(
                    float(st_obj.session_state.get(_k("width"), 12.8))
                    / ASPECT_RATIO_MAP[aspect],
                    1,
                )
            elif _k("height") not in st_obj.session_state:
                st_obj.session_state[_k("height")] = 7.2
            size_row[2].number_input(
                "高度",
                min_value=3.0,
                max_value=20.0,
                step=0.1,
                key=_k("height"),
                help="图高度（英寸）；选择纵横比后自动跟随宽度。",
            )

            # 第三行：分面行数 / 列数（勾选后显示）。
            if facet_on:
                facet_row = tab_canvas.columns(2)
                facet_row[0].number_input(
                    "分面行数",
                    min_value=0,
                    max_value=10,
                    value=0,
                    step=1,
                    key=_k("facet_rows"),
                    help="页面分面行数；0 表示自动。",
                )
                facet_row[1].number_input(
                    "分面列数",
                    min_value=0,
                    max_value=10,
                    value=0,
                    step=1,
                    key=_k("facet_cols"),
                    help="页面分面列数；0 表示自动，未指定时默认每行最多 2 个图。",
                )
            else:
                st_obj.session_state.pop(_k("facet_rows"), None)
                st_obj.session_state.pop(_k("facet_cols"), None)

            # 第四行：网格样式 / 网格线粗度 / 网格线样式。
            grid_row = tab_canvas.columns(3)
            grid_style = grid_row[0].selectbox(
                "网格样式",
                options=list(GRID_STYLES),
                index=3,
                key=_k("grid_style"),
                help="纵网格=竖直网格线；横网格=水平网格线；纵横网格=两者。",
            )
            if grid_style != "不显示":
                grid_row[1].slider(
                    "网格线粗度",
                    min_value=GRID_WIDTH_RANGE[0],
                    max_value=GRID_WIDTH_RANGE[1],
                    value=0.6,
                    step=0.1,
                    key=_k("grid_width"),
                    help="网格线的粗细（点数）。",
                )
                grid_row[2].selectbox(
                    "网格线样式",
                    options=list(GRID_LINESTYLES),
                    index=0,
                    key=_k("grid_linestyle"),
                )
            else:
                st_obj.session_state.pop(_k("grid_width"), None)
                st_obj.session_state.pop(_k("grid_linestyle"), None)

        with tab_title:
            # 第一行：图标题内容 / 标题位置。
            title_row = tab_title.columns(3)
            title_row[0].text_input(
                "图标题内容",
                value="",
                key=_k("title"),
                help="填写后显示在图中；留空不显示。",
            )
            title_row[1].selectbox(
                "标题位置",
                options=list(TITLE_POSITIONS),
                index=1,
                key=_k("title_pos"),
                help="图标题位置：左上 / 上居中 / 右上 / 下居中。",
            )
            title_row[2].number_input(
                "标题间距",
                min_value=0.0,
                max_value=40.0,
                value=12.0,
                step=1.0,
                key=_k("title_pad"),
                help="图标题与绘图区之间的间距（点）。",
            )

            # 第二行：X 轴标题内容 / X 轴标题位置。
            x_title_row = tab_title.columns(2)
            x_title_row[0].text_input(
                "X 轴标题内容",
                value="",
                key=_k("xtitle"),
                help="填写后显示；留空不显示。",
            )
            x_title_row[1].selectbox(
                "X 轴标题位置",
                options=list(XTITLE_LOCATIONS),
                index=1,
                key=_k("xtitle_loc"),
                help="X 轴标题水平对齐：左 / 中 / 右。",
            )

            # 第三行：Y 轴标题内容 / Y 轴标题位置。
            y_title_row = tab_title.columns(2)
            y_title_row[0].text_input(
                "Y 轴标题内容",
                value="",
                key=_k("ytitle"),
                help="填写后显示；留空不显示。",
            )
            y_title_row[1].selectbox(
                "Y 轴标题位置",
                options=list(YTITLE_POSITIONS),
                index=0,
                key=_k("ytitle_pos"),
                help="置顶横排（丁字：竖是轴、横是标题）；侧边为传统竖排在轴侧。",
            )

            # 第四行（联动）：第二/第三纵轴标题——在「坐标轴」tab 勾选
            # 了对应纵轴才弹出（控件渲染晚于读取，取上一次 session_state）。
            auto_dual_y_on = bool(
                st_obj.session_state.get(_k("auto_dual_y"), False)
            ) and not facet_on
            second_axis_on = bool(
                st_obj.session_state.get(_k("second_axis_on"), False)
            ) and not auto_dual_y_on
            third_axis_on = bool(
                st_obj.session_state.get(_k("third_axis_on"), False)
            ) and not auto_dual_y_on
            if second_axis_on or third_axis_on:
                axis_title_row = tab_title.columns(
                    2 if (second_axis_on and third_axis_on) else 1
                )
                column_index = 0
                if second_axis_on:
                    axis_title_row[column_index].text_input(
                        "第二纵轴标题",
                        value="",
                        key=_k("second_axis_title"),
                        help="第二纵轴（右侧内层）的标题；留空只显示单位。",
                    )
                    column_index += 1
                if third_axis_on:
                    axis_title_row[column_index].text_input(
                        "第三纵轴标题",
                        value="",
                        key=_k("third_axis_title"),
                        help="第三纵轴（最外层）的标题；留空只显示单位。",
                    )

        with tab_axis:
            # 第一行：轴开关排——年份标尺 / 自动多纵轴 / 手动第二纵轴 /
            # 手动第三纵轴 / 分面共享 X 轴 / 分面共享 Y 轴。
            toggle_row = tab_axis.columns(6)
            toggle_row[0].checkbox(
                "年份标尺",
                value=False,
                key=_k("year_ruler"),
                help="绘制严格月刻度并在 X 轴下方标注年份标尺（月度数据）。",
            )
            auto_dual_y = toggle_row[1].checkbox(
                "自动多纵轴",
                value=False,
                key=_k("auto_dual_y"),
                help="按序列尺度自动分组并创建右侧纵轴；开启后忽略手动第二/第三纵轴选择。",
                disabled=facet_on,
            )
            second_axis_requested = toggle_row[2].checkbox(
                "第二纵轴",
                value=False,
                key=_k("second_axis_on"),
                help="勾选后在底部显示「第二纵轴变量」选择栏。",
                disabled=auto_dual_y or facet_on,
            )
            third_axis_requested = toggle_row[3].checkbox(
                "第三纵轴",
                value=False,
                key=_k("third_axis_on"),
                help="勾选后在底部显示「第三纵轴变量」选择栏。",
                disabled=auto_dual_y or facet_on,
            )
            second_axis_on = bool(second_axis_requested and not auto_dual_y)
            third_axis_on = bool(third_axis_requested and not auto_dual_y)
            toggle_row[4].checkbox(
                "分面共享 X 轴",
                value=True,
                key=_k("sharex"),
                help="当前页面级分面由独立图组成，无法共享 X 轴；此项仅保留为 Ts 原生分面参数。",
                disabled=True,
            )
            toggle_row[5].checkbox(
                "分面共享 Y 轴",
                value=False,
                key=_k("sharey"),
                help="当前页面级分面由独立图组成，无法共享 Y 轴；此项仅保留为 Ts 原生分面参数。",
                disabled=True,
            )

            # 第二行：Y 轴相关——起点 / 标签数 / 刻度数 / 对数尺度。
            y_row = tab_axis.columns(4)
            y_row[0].text_input(
                "Y 轴起点",
                value="",
                key=_k("ymin"),
                help="留空自动；只支持固定起点，终点始终自动。",
            )
            y_row[1].number_input(
                "Y 轴标签数",
                min_value=1,
                max_value=40,
                value=5,
                step=1,
                key=_k("ylabel_count"),
                help="Y 轴最多显示的刻度标签数（刻度保留、标签均匀抽稀）。",
            )
            y_row[2].number_input(
                "Y 轴刻度数",
                min_value=0,
                max_value=20,
                value=0,
                step=1,
                key=_k("ytick_count"),
                help="每两个标签之间显示的子刻度线数；0 表示不显示。",
            )
            y_row[3].multiselect(
                "Y 轴对数尺度",
                options=selected,
                key=_k("log_vars"),
                help="选中变量的所在轴使用对数尺度；留空全部线性。",
            )

            # 第三行：时间轴相关——起点 / 标签数 / 刻度数。
            x_row = tab_axis.columns(4)
            x_row[0].text_input(
                "X 轴起点",
                value="",
                key=_k("xmin"),
                help="时间轴填日期（如 2020-04-01），数值轴填数字；留空自动。",
            )
            x_row[1].number_input(
                "X 轴标签数",
                min_value=1,
                max_value=40,
                value=12,
                step=1,
                key=_k("xlabel_count"),
                help="X 轴最多显示的刻度标签数（刻度保留、标签均匀抽稀）。",
            )
            x_row[2].number_input(
                "X 轴刻度数",
                min_value=0,
                max_value=20,
                value=0,
                step=1,
                key=_k("xtick_count"),
                help="每两个标签之间显示的子刻度线数；0 表示不显示。",
            )
            x_row[3].number_input(
                "自动 X 刻度上限",
                min_value=1,
                max_value=40,
                value=12,
                step=1,
                key=_k("max_ticks"),
                help="Ts 自动计算 X 轴刻度时使用的最大刻度数。",
            )

            # 第四行：自动轴分组 / 纵轴上限 / 主轴单位 / 分变量单位。
            axis_settings_row = tab_axis.columns(4)
            axis_settings_row[0].number_input(
                "自动轴尺度阈值",
                min_value=1.0,
                max_value=1000.0,
                value=10.0,
                step=0.5,
                key=_k("scale_ratio_threshold"),
                help="相邻序列尺度比达到该值时开始新的自动纵轴分组。",
            )
            axis_settings_row[1].number_input(
                "最大纵轴数",
                min_value=1,
                max_value=3,
                value=3,
                step=1,
                key=_k("max_y_axes"),
                help="包括左侧主轴在内的最大纵轴数量。",
            )
            axis_settings_row[2].text_input(
                "主 Y 轴单位",
                value="",
                key=_k("unit"),
                help="例如：%、亿元；留空不显示单位。",
            )
            axis_settings_row[3].text_input(
                "变量单位映射",
                value="",
                key=_k("units"),
                help="按变量填写：变量=单位,变量=单位；变量名必须来自当前选择。",
            )
            tab_axis.text_input(
                "显式轴分组",
                value="",
                key=_k("axis_groups"),
                help="按变量填写：变量=组名,变量=组名；同组变量共用纵轴，优先于自动分组。",
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
                        key=_k("second_axis"),
                        help="选中变量画在右侧内层第二纵轴；留空不画。",
                    )
                    column_index += 1
                if third_axis_on:
                    axis_vars_row[column_index].multiselect(
                        "第三纵轴变量",
                        options=selected,
                        key=_k("third_axis"),
                        help="选中变量画在最外层第三纵轴；留空不画。",
                    )
            else:
                st_obj.session_state.pop(_k("second_axis"), None)
                st_obj.session_state.pop(_k("third_axis"), None)

        with tab_lines:
            st_obj.caption(
                "每个变量单独设置颜色、线型、标记和尺寸；颜色仅可从 Ts 默认模板中选择。"
            )
            if not selected:
                st_obj.info("请先选择指标，再设置各指标的线条样式。")
            for index, variable in enumerate(selected):
                row = tab_lines.columns(7)
                row[0].markdown(f"**{variable}**")
                row[1].selectbox(
                    "颜色",
                    options=list(DEFAULT_PALETTE),
                    index=index % len(DEFAULT_PALETTE),
                    format_func=_format_series_color,
                    key=series_style_widget_key(
                        key_prefix, variable, "color"
                    ),
                )
                row[2].selectbox(
                    "线型",
                    options=list(SERIES_LINESTYLES),
                    index=index % len(SERIES_LINESTYLES),
                    key=series_style_widget_key(
                        key_prefix, variable, "linestyle"
                    ),
                )
                row[3].selectbox(
                    "标记",
                    options=list(SERIES_MARKERS),
                    index=list(SERIES_MARKERS).index(
                        DEFAULT_MARKERS[index % len(DEFAULT_MARKERS)]
                    ),
                    format_func=lambda marker: SERIES_MARKER_LABELS[marker],
                    key=series_style_widget_key(
                        key_prefix, variable, "marker"
                    ),
                )
                row[4].slider(
                    "线宽",
                    min_value=LINE_WIDTH_RANGE[0],
                    max_value=LINE_WIDTH_RANGE[1],
                    value=1.5,
                    step=0.5,
                    key=series_style_widget_key(
                        key_prefix, variable, "linewidth"
                    ),
                )
                row[5].slider(
                    "标记大小",
                    min_value=MARKER_SIZE_RANGE[0],
                    max_value=MARKER_SIZE_RANGE[1],
                    value=0,
                    step=1,
                    help="0 表示不显示标记。",
                    key=series_style_widget_key(
                        key_prefix, variable, "markersize"
                    ),
                )
                row[6].slider(
                    "标记描边宽度",
                    min_value=MARKER_EDGE_RANGE[0],
                    max_value=MARKER_EDGE_RANGE[1],
                    value=2.5,
                    step=0.5,
                    key=series_style_widget_key(
                        key_prefix, variable, "marker_edge"
                    ),
                )

            # 参考线与阴影：统一放在线条样式 Tab。
            vertical_row = tab_lines.columns(4)
            vertical_row[0].text_input(
                "垂直参考线",
                value="",
                key=_k("vlines"),
                help="逗号分隔：行号或日期，如 0,3,7 或 1987-07,1989-06；"
                "日期取第一个不早于该日期的数据点；留空不显示。",
            )
            vertical_row[1].selectbox(
                "垂直参考线颜色",
                options=list(COLOR_NAMES),
                index=0,
                key=_k("vline_color"),
            )
            vertical_row[2].selectbox(
                "垂直参考线样式",
                options=list(REFERENCE_LINE_STYLES),
                index=1,
                key=_k("vline_style"),
            )
            vertical_row[3].slider(
                "垂直参考线宽度",
                min_value=0.2,
                max_value=5.0,
                value=1.5,
                step=0.1,
                key=_k("vline_linewidth"),
            )

            horizontal_row = tab_lines.columns(4)
            horizontal_row[0].text_input(
                "水平参考线",
                value="",
                key=_k("hlines"),
                help="逗号分隔的 Y 轴数值，如 0,10,100；留空不显示。",
            )
            horizontal_row[1].selectbox(
                "水平参考线颜色",
                options=list(COLOR_NAMES),
                index=0,
                key=_k("hline_color"),
            )
            horizontal_row[2].selectbox(
                "水平参考线样式",
                options=list(REFERENCE_LINE_STYLES),
                index=1,
                key=_k("hline_style"),
            )
            horizontal_row[3].slider(
                "水平参考线宽度",
                min_value=0.2,
                max_value=5.0,
                value=1.5,
                step=0.1,
                key=_k("hline_linewidth"),
            )
            shade_row = tab_lines.columns(3)
            shade_row[0].text_input(
                "阴影区间",
                value="",
                key=_k("shade"),
                help="两两一组（起,止），逗号分隔，如 1987-07,1989-06 或"
                " 2,10,20,30（行号）；日期取第一个不早于该日期的数据点；"
                "留空不显示。",
            )
            shade_row[1].selectbox(
                "阴影颜色",
                options=list(COLOR_NAMES),
                index=6,
                key=_k("shade_color"),
            )
            shade_row[2].slider(
                "阴影透明度",
                min_value=0.0,
                max_value=1.0,
                value=0.3,
                step=0.1,
                key=_k("shade_alpha"),
            )

        with tab_legend:
            # 第一行：显示图例 / 标注开关 / 数值小数位。
            toggle_row = tab_legend.columns(3)
            show_legend = toggle_row[0].checkbox(
                "显示图例",
                value=True,
                key=_k("legend"),
            )
            show_values = toggle_row[1].checkbox(
                "标注数据值",
                value=False,
                key=_k("show_values"),
                help="在每个数据点旁标注数值。",
            )
            if show_values:
                toggle_row[2].number_input(
                    "数值小数位",
                    min_value=0,
                    max_value=6,
                    value=1,
                    step=1,
                    key=_k("value_decimals"),
                )
            else:
                st.session_state.pop(_k("value_decimals"), None)

            if show_legend:
                # 第二行：图例位置 / 图例标题 / 图例列数 / 图例字号。
                row = tab_legend.columns(4)
                row[0].selectbox(
                    "图例位置",
                    options=list(LEGEND_LOCATIONS),
                    index=0,
                    key=_k("legend_loc"),
                    help=(
                        "默认（best）图例置底；选择其他位置后"
                        "按所选位置显示。"
                    ),
                )
                row[1].text_input(
                    "图例标题",
                    value="",
                    key=_k("legend_title"),
                    help="图例上方的小标题（如：变量）；留空不显示。",
                )
                row[2].number_input(
                    "图例列数",
                    min_value=1,
                    max_value=8,
                    value=1,
                    step=1,
                    key=_k("legend_cols"),
                    help="叠加图中图例条目排成几列；页面级分面每个图只有一个条目。",
                    disabled=facet_on,
                )
                row[3].number_input(
                    "图例字号",
                    min_value=8.0,
                    max_value=30.0,
                    value=None,
                    step=0.5,
                    key=_k("legend_size"),
                    placeholder="自动匹配图大小",
                    help="留空时根据图形宽高自动匹配图例和内部文字大小。",
                )

                # 第三行：自定义图例标签 / 图例锚点 X / 图例锚点 Y。
                legend_location = st_obj.session_state.get(
                    _k("legend_loc"), "best"
                )
                legend_anchor_enabled = legend_location != "best" and not facet_on
                label_row = tab_legend.columns(3)
                label_row[0].text_input(
                    "自定义图例标签",
                    value="",
                    key=_k("legend_labels"),
                    help="按当前变量选择顺序填写，逗号分隔；留空使用变量名。",
                )
                label_row[1].number_input(
                    "图例锚点 X",
                    min_value=-2.0,
                    max_value=3.0,
                    value=None,
                    step=0.05,
                    key=_k("legend_bbox_x"),
                    disabled=not legend_anchor_enabled,
                    placeholder="自动",
                    help="叠加图选择明确位置后生效；页面级分面不支持外置锚点。",
                )
                label_row[2].number_input(
                    "图例锚点 Y",
                    min_value=-2.0,
                    max_value=3.0,
                    value=None,
                    step=0.05,
                    key=_k("legend_bbox_y"),
                    disabled=not legend_anchor_enabled,
                    placeholder="自动",
                    help="叠加图选择明确位置后生效；页面级分面不支持外置锚点。",
                )
            else:
                for name in (
                    "legend_loc",
                    "legend_title",
                    "legend_cols",
                    "legend_size",
                    "legend_labels",
                    "legend_bbox_x",
                    "legend_bbox_y",
                ):
                    st_obj.session_state.pop(_k(name), None)

            # 图注设置——内容（最左）/ 位置 / 自动前缀。
            note_row = tab_legend.columns(3)
            note_row[0].text_input(
                "图注内容",
                value="",
                key=_k("note"),
                help="填写后显示在图中下方；留空不显示。",
            )
            note_row[1].selectbox(
                "图注位置",
                options=list(NOTE_LOCATIONS),
                index=0,
                key=_k("note_loc"),
                help="图注在图中下方的水平位置：左 / 中 / 右。",
            )
            note_row[2].text_input(
                "自动前缀",
                value="数据来源：",
                key=_k("note_prefix"),
                help="自动加在图注内容前的文字；留空不显示前缀。",
            )



__all__ = ["render_chart_options_expander"]
