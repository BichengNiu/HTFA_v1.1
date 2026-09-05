"""数据预览图适配层的渲染契约测试。"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

import htfa.ui_shared.data_overview.ui.chart_panel as chart_panel
from htfa.ui_shared.data_overview.ui.chart_panel import draw_series_plot
from htfa.ui_shared.data_overview.ui.legend import place_chart_legend_at_bottom
from Ts.TsPlots import plot_series


class _StreamlitStub:
    """Capture the figure passed to Streamlit without starting Streamlit."""

    def pyplot(self, figure, **_kwargs):
        self.figure = figure


def _dataset(frame):
    return SimpleNamespace(frame=frame, time_column=None)


def test_marker_size_zero_does_not_add_sparse_secondary_markers():
    """用户关闭标记时，适配层不得再额外补点。"""
    index = pd.date_range("2024-01-01", periods=20, freq="D")
    frame = pd.DataFrame(
        {
            "main": np.arange(20, dtype=float),
            "sparse": [np.nan] * 17 + [10.0, 11.0, 12.0],
        },
        index=index,
    )
    streamlit = _StreamlitStub()

    draw_series_plot(
        streamlit,
        _dataset(frame),
        ["main", "sparse"],
        facet=False,
        second_axis_vars=["sparse"],
        marker_size=0,
        figsize=(6, 4),
        filtered=frame,
    )

    axis = streamlit.figure.axes[0]
    right_axis = axis.extra_y_axes[0]
    assert len(right_axis.lines) == 1


def test_configured_figsize_is_preserved():
    """用户设置的画布尺寸应成为最终渲染尺寸。"""
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    streamlit = _StreamlitStub()

    draw_series_plot(
        streamlit,
        _dataset(frame),
        ["a"],
        figsize=(6, 4),
        filtered=frame,
    )

    assert tuple(streamlit.figure.get_size_inches()) == (6.0, 4.0)


def test_plot_starts_at_first_valid_observation():
    """图表裁掉首个有效值之前的空时间点。"""
    index = pd.date_range("2000-01-01", periods=4, freq="YS")
    frame = pd.DataFrame({"value": [np.nan, np.nan, 10.0, 11.0]}, index=index)
    streamlit = _StreamlitStub()

    draw_series_plot(
        streamlit,
        _dataset(frame),
        ["value"],
        figsize=(6, 4),
        filtered=frame,
    )

    plotted_x = streamlit.figure.axes[0].lines[0].get_xdata()
    assert plotted_x[0] == index[2]


def test_non_bottom_legend_receives_title_and_column_count():
    """非底部图例位置也应接收 Ts 的标题和列数参数。"""
    frame = pd.DataFrame(
        {"a": [1.0, 2.0], "b": [2.0, 3.0], "c": [3.0, 4.0]}
    )
    streamlit = _StreamlitStub()

    draw_series_plot(
        streamlit,
        _dataset(frame),
        ["a", "b", "c"],
        legend_loc="upper left",
        legend_title="变量",
        legend_cols=2,
        figsize=(6, 4),
        filtered=frame,
    )

    legend = streamlit.figure.axes[0].get_legend()
    assert legend is not None
    assert legend.get_title().get_text() == "变量"
    assert legend._ncols == 2


def test_single_series_non_bottom_legend_is_visible_with_explicit_label():
    """页面级分面传入变量名后，显式位置的单序列图例可见。"""
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    streamlit = _StreamlitStub()

    draw_series_plot(
        streamlit,
        _dataset(frame),
        ["a"],
        legend_loc="upper right",
        legend_labels=["a"],
        figsize=(6, 4),
        filtered=frame,
    )

    legend = streamlit.figure.axes[0].get_legend()
    assert legend is not None
    assert [text.get_text() for text in legend.get_texts()] == ["a"]


def test_extended_ts_options_are_forwarded(monkeypatch):
    """新增高级选项应逐项转发到 Ts plot_series。"""
    frame = pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 3.0]})
    streamlit = _StreamlitStub()
    captured = {}
    original_plot_series = chart_panel.plot_series

    def wrapped_plot_series(data, **kwargs):
        captured.update(kwargs)
        return original_plot_series(data, **kwargs)

    monkeypatch.setattr(chart_panel, "plot_series", wrapped_plot_series)
    draw_series_plot(
        streamlit,
        _dataset(frame),
        ["a", "b"],
        max_ticks=20,
        legend_labels=["产出", "增速"],
        legend_bbox=(1.1, 0.9),
        legend_size=11.0,
        title_pad=18,
        sharex=False,
        auto_dual_y=True,
        scale_ratio_threshold=25.0,
        axis_groups={"a": "左轴", "b": "右轴"},
        max_y_axes=2,
        unit="亿元",
        units={"a": "亿元", "b": "%"},
        colors=["#d9534f", "#123456"],
        hlines=[1.5],
        hline_color="#123456",
        hline_linestyle=":",
        hline_linewidth=2.25,
        vline_linewidth=2.0,
        figsize=(6, 4),
        filtered=frame,
    )

    assert captured["max_ticks"] == 20
    assert captured["legend_labels"] == ["产出", "增速"]
    assert captured["legend_bbox"] == (1.1, 0.9)
    assert captured["legend_size"] == 11.0
    assert captured["title_pad"] == 18
    assert captured["sharex"] is False
    assert captured["auto_dual_y"] is True
    assert captured["scale_ratio_threshold"] == 25.0
    assert captured["axis_groups"] == {"a": "左轴", "b": "右轴"}
    assert captured["max_y_axes"] == 2
    assert captured["unit"] == "亿元"
    assert captured["units"] == {"a": "亿元", "b": "%"}
    assert captured["colors"] == ["#d9534f", "#123456"]
    assert captured["hlines"] == [1.5]
    assert captured["hline_color"] == "#123456"
    assert captured["hline_linestyle"] == ":"
    assert captured["hline_linewidth"] == 2.25
    assert captured["vline_linewidth"] == 2.0


def test_hidden_legend_is_not_recreated_by_bottom_renderer():
    """关闭图例后，底部适配器不得重新创建图例。"""
    frame = pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 3.0]})
    streamlit = _StreamlitStub()

    draw_series_plot(
        streamlit,
        _dataset(frame),
        ["a", "b"],
        show_legend=False,
        legend_loc="best",
        figsize=(6, 4),
        filtered=frame,
    )

    assert not streamlit.figure.legends
    assert streamlit.figure.axes[0].get_legend() is None


def test_secondary_axis_series_is_in_preview_legend():
    """数据预览底部图例应包含第二纵轴变量。"""
    index = pd.date_range("2024-01-01", periods=4, freq="D")
    frame = pd.DataFrame(
        {"main": [1.0, 2.0, 3.0, 4.0], "secondary": [10.0, 11.0, 12.0, 13.0]},
        index=index,
    )
    figure, _axis = plot_series(
        frame,
        facet=False,
        auto_dual_y=False,
        second_axis_vars=["secondary"],
        markersize=0,
    )

    place_chart_legend_at_bottom(figure)

    labels = [text.get_text() for text in figure.legends[0].get_texts()]
    assert labels == ["main", "secondary"]
