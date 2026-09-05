from matplotlib.figure import Figure
import plotly.graph_objects as go

from htfa.ui_shared.chart_legend import place_chart_legend_at_bottom


def test_plotly_legend_is_forced_to_bottom() -> None:
    figure = go.Figure()
    figure.add_scatter(x=[1, 2], y=[2, 3], name="序列A")
    figure.update_layout(
        legend={"orientation": "v", "y": 1.0, "x": 1.0},
        margin={"b": 20},
    )

    result = place_chart_legend_at_bottom(figure)

    assert result is figure
    assert figure.layout.legend.orientation == "h"
    assert figure.layout.legend.y < 0
    assert figure.layout.legend.x == 0.5
    assert figure.layout.margin.b >= 120


def test_matplotlib_axis_legend_is_moved_to_figure_bottom() -> None:
    figure = Figure()
    axis = figure.add_subplot(111)
    axis.plot([1, 2], [2, 3], label="序列A")
    axis.legend(loc="upper right")

    result = place_chart_legend_at_bottom(figure)

    assert result is figure
    assert axis.get_legend() is None
    assert len(figure.legends) == 1
    assert figure.legends[0].get_bbox_to_anchor()._bbox.y0 < 0.2


def test_matplotlib_secondary_axis_without_local_legend_is_collected() -> None:
    """右侧纵轴曲线也应出现在底部图例中。"""
    figure = Figure()
    axis = figure.add_subplot(111)
    axis.plot([1, 2], [2, 3], label="主变量")
    axis.legend(loc="upper right")
    right_axis = axis.twinx()
    right_axis.plot([1, 2], [20, 30], label="第二变量")

    place_chart_legend_at_bottom(figure)

    labels = [text.get_text() for text in figure.legends[0].get_texts()]
    assert labels == ["主变量", "第二变量"]


def test_plotly_chart_without_legend_keeps_its_existing_margin() -> None:
    figure = go.Figure()
    figure.add_bar(x=[1, 2], y=[2, 3], showlegend=False)
    figure.update_layout(showlegend=False, margin={"b": 25})

    place_chart_legend_at_bottom(figure)

    assert figure.layout.margin.b == 25
