"""Matplotlib 图例置底布局与图形渲染工具（零项目依赖，可整体拷走）。"""

from __future__ import annotations

import math
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure as MatplotlibFigure
from plotly.graph_objects import Figure as PlotlyFigure
from Ts.TsPlots.style import LEGEND_FONTSIZE, resolve_legend_fontsize


PLOTLY_LEGEND_Y = -0.14

# 图例区物理尺寸（英寸）预留，按图高换算为比例：X 轴标题（时间列名）
# 与图例各占一段并留出安全间距，任何图高下两者都不重叠、也不远离轴。
_XLABEL_INCHES = 0.32
_LEGEND_ROW_INCHES = 0.60
_LEGEND_BAND_PAD_INCHES = 0.45


def _legend_band_height(figure: MatplotlibFigure, rows: int) -> float:
    """底部留白比例：X 轴标题 + 图例区 + 安全间距。"""
    inches = (
        _XLABEL_INCHES + _LEGEND_ROW_INCHES * rows + _LEGEND_BAND_PAD_INCHES
    )
    return inches / figure.get_figheight()


def _legend_anchor_y(figure: MatplotlibFigure) -> float:
    """图例下边缘锚点比例：紧贴 X 轴标题下方，互不重叠。"""
    return _XLABEL_INCHES / figure.get_figheight()


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
    legend_size: float | None = None,
) -> None:
    handles: list[Any] = []
    labels: list[str] = []
    for axis in figure.axes:
        legend = axis.get_legend()
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
        fontsize = resolve_legend_fontsize(figure, legend_size)
        scale = fontsize / LEGEND_FONTSIZE
        figure.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, _legend_anchor_y(figure)),
            ncol=ncol,
            frameon=False,
            fontsize=fontsize,
            markerscale=1.6 * scale,
            handlelength=2.6 * scale,
            title=legend_title or None,
            title_fontsize=fontsize,
        )

    for legend in figure.legends:
        if hasattr(legend, "set_loc"):
            legend.set_loc("lower center")
        legend.set_bbox_to_anchor(
            (0.5, _legend_anchor_y(figure)),
            transform=figure.transFigure,
        )

    if figure.legends:
        # 底部留白只占轴标题与图例区的实际所需：宽幅图下既不出现
        # 大段空白，图例也不会压到 X 轴标题。
        figure.subplots_adjust(
            bottom=max(figure.subplotpars.bottom, _legend_band_height(figure, rows))
        )


def place_chart_legend_at_bottom(
    figure: Any,
    *,
    legend_title: str | None = None,
    legend_cols: int | None = None,
    legend_size: float | None = None,
) -> Any:
    """原地应用全局图例布局规则，并返回原图表对象。

    legend_title：图例上方标题（None 不显示）；legend_cols：图例列数
    （None 时按条目数自动，最多 4 列）。
    """

    if isinstance(figure, PlotlyFigure):
        _place_plotly_legend_at_bottom(figure)
    elif isinstance(figure, MatplotlibFigure):
        _place_matplotlib_legend_at_bottom(
            figure,
            legend_title=legend_title,
            legend_cols=legend_cols,
            legend_size=legend_size,
        )
    return figure


def render_pyplot_figure(
    st_obj,
    figure: MatplotlibFigure,
    *,
    place_legend_bottom: bool = True,
    legend_title: str | None = None,
    legend_cols: int | None = None,
    legend_size: float | None = None,
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
                legend_size=legend_size,
            )
        st_obj.pyplot(figure, **kwargs)
    finally:
        plt.close(figure)


__all__ = ["place_chart_legend_at_bottom", "render_pyplot_figure"]
