"""数据概览的图侧面板：调用 Ts plot_series 渲染预览图。

签名与 Ts plot_series 参数一一对应（auto_dual_y 固定 False），
是组件 UI 层与 Ts 包底层的参数契约收口点。外部依赖：Ts 包。
"""

from __future__ import annotations

import logging

from Ts.TsPlots import plot_series

from ..core.constants import PREVIEW_DPI, PREVIEW_FIGSIZE
from htfa.ui_shared.matplotlib_compat import matplotlib_date_compatibility
from ..core.options import trim_to_valid_range
from .legend import render_pyplot_figure

logger = logging.getLogger(__name__)


def draw_series_plot(
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
    max_ticks: int = 12,
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
    legend_labels=None,
    legend_bbox=None,
    legend_title: str | None = None,
    legend_cols: int | None = None,
    legend_size: float | None = None,
    title_loc: str = "center",
    title_pad: float = 12,
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
    sharex: bool = True,
    sharey: bool = False,
    auto_dual_y: bool = False,
    scale_ratio_threshold: float = 10.0,
    axis_groups=None,
    max_y_axes: int = 3,
    second_axis_vars: list[str] | None = None,
    third_axis_vars: list[str] | None = None,
    second_axis_title: str | None = None,
    third_axis_title: str | None = None,
    log_vars: list[str] | None = None,
    unit: str | None = None,
    units=None,
    colors=None,
    series_styles=None,
    vlines=None,
    hlines=None,
    vline_color: str = "#d9534f",
    vline_linestyle: str = "--",
    vline_linewidth: float = 1.5,
    hline_color: str = "#d9534f",
    hline_linestyle: str = "--",
    hline_linewidth: float = 1.5,
    shade=None,
    shade_color: str = "#d0d0d0",
    shade_alpha: float = 0.3,
    filtered=None,
) -> None:
    """调用 TsPlots.plot_series 绘制所选变量，并渲染到页面。

    filtered：筛选后的数据框（与 dataset.frame 同结构）；传入时
    只绘制筛选范围内且处于有效观测首尾范围内的序列，与上方预览表一致。
    """
    source = filtered if filtered is not None else dataset.frame
    source = trim_to_valid_range(source, variables)
    if source.empty:
        st_obj.info("所选指标没有有效观测，暂无时间序列图可绘制。")
        return
    if dataset.time_column is not None:
        plot_frame = source.set_index(dataset.time_column).loc[:, variables]
        default_xtitle = dataset.time_column
    else:
        plot_frame = source.loc[:, variables]
        default_xtitle = "观测序号"

    effective_figsize = figsize or PREVIEW_FIGSIZE

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
            max_ticks=max_ticks,
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
            legend_labels=legend_labels,
            legend_bbox=legend_bbox,
            title_loc=title_loc,
            title_pad=title_pad,
            title_position=title_position,
            note=note,
            note_loc=note_loc,
            note_prefix=note_prefix,
            show_values=show_values,
            value_decimals=value_decimals,
            facet=facet,
            facet_rows=facet_rows,
            facet_cols=facet_cols,
            figsize=effective_figsize,
            sharex=sharex,
            sharey=sharey,
            auto_dual_y=auto_dual_y,
            scale_ratio_threshold=scale_ratio_threshold,
            axis_groups=axis_groups,
            max_y_axes=max_y_axes,
            second_axis_vars=second_axis_vars,
            third_axis_vars=third_axis_vars,
            second_axis_title=second_axis_title,
            third_axis_title=third_axis_title,
            log_vars=log_vars,
            unit=unit,
            units=units,
            colors=colors,
            series_styles=series_styles,
            legend_title=legend_title,
            legend_cols=legend_cols,
            legend_size=legend_size,
            vlines=vlines,
            hlines=hlines,
            vline_color=vline_color,
            vline_linestyle=vline_linestyle,
            vline_linewidth=vline_linewidth,
            hline_color=hline_color,
            hline_linestyle=hline_linestyle,
            hline_linewidth=hline_linewidth,
            shade=shade,
            shade_color=shade_color,
            shade_alpha=shade_alpha,
        )
    except Exception:
        logger.exception("数据概览时间序列预览绘图失败")
        raise

    fig.set_dpi(PREVIEW_DPI)
    with matplotlib_date_compatibility():
        render_pyplot_figure(
            st_obj,
            fig,
            place_legend_bottom=(show_legend and legend_loc == "best"),
            legend_title=legend_title,
            legend_cols=legend_cols,
            legend_size=legend_size,
        )


__all__ = ["draw_series_plot"]
