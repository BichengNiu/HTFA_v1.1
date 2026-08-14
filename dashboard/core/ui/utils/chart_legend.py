"""HTFA 全局图例布局规则。"""

from __future__ import annotations

from typing import Any

from matplotlib.figure import Figure as MatplotlibFigure
from plotly.graph_objects import Figure as PlotlyFigure


PLOTLY_LEGEND_Y = -0.14
MATPLOTLIB_LEGEND_Y = 0.115


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


def _place_matplotlib_legend_at_bottom(figure: MatplotlibFigure) -> None:
    handles: list[Any] = []
    labels: list[str] = []
    for axis in figure.axes:
        legend = axis.get_legend()
        if legend is None:
            continue
        axis_handles, axis_labels = axis.get_legend_handles_labels()
        for handle, label in zip(axis_handles, axis_labels):
            if label and label not in labels:
                handles.append(handle)
                labels.append(label)
        legend.remove()

    if handles:
        figure.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, MATPLOTLIB_LEGEND_Y),
            ncol=min(4, len(labels)),
            frameon=False,
        )

    for legend in figure.legends:
        if hasattr(legend, "set_loc"):
            legend.set_loc("lower center")
        legend.set_bbox_to_anchor(
            (0.5, MATPLOTLIB_LEGEND_Y),
            transform=figure.transFigure,
        )

    if figure.legends:
        figure.subplots_adjust(bottom=max(figure.subplotpars.bottom, 0.32))


def place_chart_legend_at_bottom(figure: Any) -> Any:
    """原地应用全局图例置底规则，并返回原图表对象。"""

    if isinstance(figure, PlotlyFigure):
        _place_plotly_legend_at_bottom(figure)
    elif isinstance(figure, MatplotlibFigure):
        _place_matplotlib_legend_at_bottom(figure)
    return figure


__all__ = ["place_chart_legend_at_bottom"]
