"""HTFA 全局图例布局规则。"""

from __future__ import annotations

import math
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure as MatplotlibFigure
from plotly.graph_objects import Figure as PlotlyFigure


PLOTLY_LEGEND_Y = -0.14

# 图例顶部在时间轴（参考轴 x 轴）下方的轴分数偏移。锚定在轴坐标系里，
# 跟随轴移动：year_ruler 年份标尺文字约在轴下方 -0.18（轴分数）处，
# -0.22 让图例顶紧贴其下，任何轴位置下都不会悬空或重叠。
_LEGEND_BELOW_AXIS_OFFSET = 0.22
# 底部留白上限：来源注释（y=0.025，va="bottom"）加字高与安全间距。
_NOTE_TOP_FRAC = 0.055
# 无渲染器环境（纯 Figure() 作图）下经验估算的图例行高（英寸）与安全间距。
_LEGEND_ROW_INCHES = 0.60
_LEGEND_BAND_PAD_INCHES = 0.45


def _place_plotly_legend_at_bottom(figure: PlotlyFigure) -> None:
    if figure.layout.showlegend is False:
        return
    has_visible_legend = any(
        trace.showlegend is not False and bool(trace.name)
        for trace in figure.data
    )
    if not has_visible_legend:
        return

    current_bottom = figure.layout.margin.b or 0
    figure.update_layout(
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": PLOTLY_LEGEND_Y,
            "xanchor": "center",
            "x": 0.5,
        },
        margin={"b": max(current_bottom, 120)},
    )


def _place_matplotlib_legend_at_bottom(
    figure: MatplotlibFigure,
    legend_title: str | None = None,
    legend_cols: int | None = None,
) -> None:
    handles: list[Any] = []
    labels: list[str] = []
    for axis in figure.axes:
        legend = axis.get_legend()
        if legend is not None:
            axis_handles = getattr(legend, "legend_handles", None)
            if axis_handles is None:
                axis_handles = getattr(legend, "legendHandles", None)
            axis_labels = [text.get_text() for text in legend.get_texts()]
        else:
            axis_handles, axis_labels = axis.get_legend_handles_labels()
        for handle, label in zip(axis_handles, axis_labels):
            if label and not label.startswith("_") and label not in labels:
                handles.append(handle)
                labels.append(label)
        if legend is not None:
            legend.remove()

    rows = 1
    if handles:
        ncol = legend_cols or min(4, len(labels))
        rows = math.ceil(len(labels) / ncol)
        figure.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.0),
            ncol=ncol,
            frameon=False,
            fontsize=15,
            markerscale=1.6,
            handlelength=2.6,
            title=legend_title or None,
            title_fontsize=15,
        )

    visible = [axis for axis in figure.axes if axis.get_visible()]
    if not figure.legends or not visible:
        return

    # 图例顶部锚在最低参考轴的时间轴下方（轴坐标），与 Ts 模板
    # ``BottomLegend`` 同款锚定：图例随轴联动，永远不会悬在底部远处。
    ref_ax = min(visible, key=lambda axis: axis.get_position().y0)
    for legend in figure.legends:
        if hasattr(legend, "set_loc"):
            legend.set_loc("upper center")
        legend.set_bbox_to_anchor(
            (0.5, -_LEGEND_BELOW_AXIS_OFFSET),
            transform=ref_ax.transAxes,
        )

    renderer = None
    try:
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
    except (AttributeError, NotImplementedError):
        renderer = None

    if renderer is None:
        # 无渲染器环境（纯 Figure() 作图）：只保证底部空间够用，不缩小。
        band = (
            _LEGEND_ROW_INCHES * rows + _LEGEND_BAND_PAD_INCHES
        ) / figure.get_figheight() + _NOTE_TOP_FRAC
        figure.subplots_adjust(bottom=max(figure.subplotpars.bottom, band))
        return

    # 图例锚在轴坐标系：调整 bottom 时图例随参考轴以 (1+offset) 倍同步
    # 移动，因此一次线性配平即可让图例底精确落在来源注释上方——双向
    # 收紧，图自身显式的大 bottom（如 bottom=0.30/0.32）不再把图例压远。
    inv = figure.transFigure.inverted()
    legend_bottom_frac = min(
        inv.transform(legend.get_window_extent(renderer).corners())[:, 1].min()
        for legend in figure.legends
    )
    raise_by = (_NOTE_TOP_FRAC - legend_bottom_frac) / (
        1 + _LEGEND_BELOW_AXIS_OFFSET
    )
    figure.subplots_adjust(bottom=figure.subplotpars.bottom + raise_by)


def place_chart_legend_at_bottom(
    figure: Any,
    *,
    legend_title: str | None = None,
    legend_cols: int | None = None,
) -> Any:
    """原地应用全局图例布局规则，并返回原图表对象。

    legend_title：图例上方标题（None 不显示）；legend_cols：图例列数
    （None 时按条目数自动，最多 4 列）。
    """

    if isinstance(figure, PlotlyFigure):
        _place_plotly_legend_at_bottom(figure)
    elif isinstance(figure, MatplotlibFigure):
        _place_matplotlib_legend_at_bottom(
            figure, legend_title=legend_title, legend_cols=legend_cols
        )
    return figure


def render_pyplot_figure(
    st_obj,
    figure: MatplotlibFigure,
    *,
    place_legend_bottom: bool = True,
    legend_title: str | None = None,
    legend_cols: int | None = None,
    **kwargs,
) -> None:
    """按全局图例规则渲染 Matplotlib 图形并关闭资源。

    place_legend_bottom=False 时跳过图例置底（图例保持在原位置，
    供用户显式选择图例位置的图表使用）。legend_title / legend_cols
    仅在置底时生效。
    """

    if "use_container_width" not in kwargs:
        kwargs.setdefault("width", "stretch")
    kwargs.setdefault("clear_figure", True)
    try:
        if place_legend_bottom:
            figure = place_chart_legend_at_bottom(
                figure,
                legend_title=legend_title,
                legend_cols=legend_cols,
            )
        st_obj.pyplot(figure, **kwargs)
    finally:
        plt.close(figure)


__all__ = ["place_chart_legend_at_bottom", "render_pyplot_figure"]
