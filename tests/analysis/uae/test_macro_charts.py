"""Macro charts use the same Ts renderer and retain independently released quarters."""

import inspect

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from htfa.monitoring.uae import charts
from htfa.ui_shared.chart_legend import _apply_cjk_fonts


def test_sector_pull_ts_chart_keeps_negative_stacks_and_separate_units():
    frame = pd.DataFrame({
        "非石油经济部门拉动": [2.0, -3.0],
        "石油经济部门拉动": [1.0, -2.0],
        "石油及其他液体产量季度同比": [10.0, -4.0],
        "实际GDP（十亿阿联酋迪拉姆）": [100.0, 95.0],
    }, index=pd.to_datetime(["2026-03-31", "2026-06-30"]))
    figure = charts.build_growth_and_sector_pull_figure(frame, title="部门拉动")
    try:
        left, right = figure.axes
        first, second = left.containers
        assert [patch.get_y() for patch in second] == [2.0, -3.0]
        assert left.get_ylim()[0] < -5.0
        assert [patch.get_x() for patch in first] == [patch.get_x() for patch in second]
        assert left.get_ylabel() == "百分点"
        assert right.get_ylabel() == "%"
        assert all(axis.get_xlabel() == "" for axis in figure.axes)
        np.testing.assert_equal(right.lines[0].get_ydata(), [10.0, -4.0])
        assert [text.get_text() for text in left.get_legend().get_texts()] == [f"{name}（左轴）" for name in frame.columns[:2]] + [f"{frame.columns[2]}（右轴）"]
    finally:
        plt.close(figure)


@pytest.mark.parametrize("sector", [False, True])
def test_long_macro_year_labels_remain_visible_with_final_cjk_fonts(sector):
    dates = pd.date_range("2013-03-31", "2026-06-30", freq="QE")
    if sector:
        frame = pd.DataFrame({
            "非石油经济部门拉动": np.ones(len(dates)),
            "石油经济部门拉动": -np.ones(len(dates)),
            "石油及其他液体产量季度同比": np.arange(len(dates)),
        }, index=dates)
        builder = charts.build_growth_and_sector_pull_figure
    else:
        frame = pd.DataFrame({
            "实际GDP当季同比": np.ones(len(dates)),
            "GDP平减指数同比": np.arange(len(dates)),
        }, index=dates)
        builder = charts.build_price_volume_figure
    figure = builder(frame, title="宏观概览")
    try:
        _apply_cjk_fonts(figure)
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        quarter_labels = figure.axes[0].get_xticklabels()
        assert quarter_labels
        assert all(label.get_text() in {"Q1", "Q2", "Q3", "Q4"}
                   for label in quarter_labels if label.get_text())
        tick_boxes = [label.get_window_extent(renderer) for label in quarter_labels
                      if label.get_text()]
        assert all(left.x1 < right.x0 for left, right in zip(tick_boxes, tick_boxes[1:]))
        labels = [text for axis in figure.axes for text in axis.texts
                  if text.get_gid() == "ts-year-ruler-label"]
        assert [text.get_text() for text in labels] == [
            "2013–2015", "2016–2018", "2019–2021", "2022–2024", "2025", "2026",
        ]
        boxes = [text.get_bbox_patch().get_window_extent(renderer) for text in labels]
        assert all(left.x1 < right.x0 for left, right in zip(boxes, boxes[1:]))
        assert all(figure.bbox.contains(box.x0, box.y0)
                   and figure.bbox.contains(box.x1, box.y1) for box in boxes)
        legends = [axis.get_legend() for axis in figure.axes if axis.get_legend()]
        assert not any(box.overlaps(legend.get_window_extent(renderer))
                       for box in boxes for legend in legends)
    finally:
        plt.close(figure)


def test_macro_ts_chart_has_no_x_title_and_keeps_real_growth_in_q2(monkeypatch):
    frame = pd.DataFrame({
        "【真实】实际GDP当季同比": [3.0, 4.0, 5.0],
        "【真实】GDP平减指数同比": [1.0, 2.0, np.nan],
    }, index=pd.to_datetime(["2025-12-31", "2026-03-31", "2026-06-30"]))
    captured = {}
    from Ts.TsPlots import plot_series

    def capture(data, **kwargs):
        inspect.signature(plot_series).bind(data, **kwargs)
        captured.update(kwargs)
        return plot_series(data, **kwargs)

    monkeypatch.setattr(charts, "plot_series", capture, raising=False)
    figure = charts.build_price_volume_figure(frame, title="GDP同比")
    assert isinstance(figure, Figure)
    axis = figure.axes[0]
    assert all(axis.get_xlabel() == "" for axis in figure.axes)
    lines = {line.get_label(): line for line in axis.lines}
    assert lines["【真实】实际GDP当季同比"].get_ydata()[-1] == 5.0
    assert np.isnan(lines["【真实】GDP平减指数同比"].get_ydata()[-1])
    assert pd.Timestamp(lines["【真实】实际GDP当季同比"].get_xdata()[-1]) == pd.Timestamp("2026-06-30")
    assert captured["xtitle"] == ""
    assert captured["facet"] is False
    assert captured["year_ruler"] is True
    assert captured["year_ruler_span"] == 3
    assert captured["quarterly_ticks"] is True
    assert all(
        label.get_text() in {"Q1", "Q2", "Q3", "Q4"}
        for label in axis.get_xticklabels() if label.get_text()
    )
    assert any(text.get_text().strip() == "2026" for text in axis.texts)
    assert "hlines" not in captured
    assert captured["legend_labels"] == ["实际GDP当季同比", "GDP平减指数同比"]
    assert [text.get_text() for text in axis.get_legend().get_texts()] == captured["legend_labels"]
    assert captured["figsize"] == (9.4, 6.2)
    assert captured["units"] == {name: "%" for name in frame}
    plt.close(figure)


def test_nonoil_industry_pull_uses_ts_with_axis_roles_and_quarters():
    frame = pd.DataFrame({
        "制造业": [2.0, -1.0, 3.0],
        "其他行业": [1.0, -2.0, 2.0],
        "非油GDP同比": [3.0, -3.0, 5.0],
    }, index=pd.date_range("2025-12-31", periods=3, freq="QE"))
    figure = charts.build_nonoil_industry_pull_figure(frame, title="非油行业拉动")
    try:
        left, right = figure.axes
        assert left.get_ylabel() == "百分点"
        assert right.get_ylabel() == "%"
        assert len(left.containers) == 2
        growth_line = next(line for line in right.lines if line.get_label() == "非油GDP同比")
        np.testing.assert_equal(growth_line.get_ydata(), frame["非油GDP同比"].to_numpy())
        assert [item.get_text() for item in left.get_legend().get_texts()] == [
            "制造业（左轴）", "其他行业（左轴）", "非油GDP同比（右轴）",
        ]
        assert [item.get_text() for item in left.get_xticklabels()] == ["Q4", "Q1", "Q2"]
    finally:
        plt.close(figure)
