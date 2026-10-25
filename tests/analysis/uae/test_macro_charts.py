"""Macro charts use the same Ts renderer and retain independently released quarters."""

import inspect

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from htfa.monitoring.uae import charts
from htfa.ui_shared.chart_legend import _apply_cjk_fonts


@pytest.mark.parametrize("max_points", [None, 65])
def test_industry_chart_windows_remain_independent_of_macro_history_limit(max_points):
    index = pd.period_range("2000Q1", periods=90, freq="Q")
    breadth = pd.DataFrame({"不加权｜正增长行业比例": 50.0,
                            "不加权｜连续四季度正增长的行业比例": 25.0}, index=index)
    concentration = pd.DataFrame({
        "贡献平衡指数": 60.0, "标准化绝对贡献集中度": 25.0,
        "绝对贡献HHI": 0.25, "总变动强度": 5.0, "非油GDP同比": 3.0,
        "最大正向贡献行业": "制造业", "最大正向贡献": 4.0,
        "最大负向贡献行业": "建筑业", "最大负向贡献": -1.0,
    }, index=index)
    options = {} if max_points is None else {"max_points": max_points}
    expected = 80 if max_points is None else max_points
    figure = charts.build_industry_breadth_figure(breadth, title="行业广度", **options)
    assert len(figure.data[0].x) == expected
    assert figure.data[0].x[0] == str(index[-expected])
    figure = charts.build_industry_concentration_figure(
        concentration, title="行业集中度", **options,
    )
    assert len(figure.frames) == expected
    assert figure.frames[0].name == str(index[-expected])


def test_sector_pull_ts_chart_keeps_negative_stacks_without_oil_production_line():
    frame = pd.DataFrame({
        "非石油经济部门拉动": [2.0, -3.0],
        "石油经济部门拉动": [1.0, -2.0],
        "石油及其他液体产量季度同比": [10.0, -4.0],
        "实际GDP（十亿阿联酋迪拉姆）": [100.0, 95.0],
    }, index=pd.to_datetime(["2026-03-31", "2026-06-30"]))
    figure = charts.build_growth_and_sector_pull_figure(frame, title="部门拉动")
    try:
        assert len(figure.axes) == 1
        left = figure.axes[0]
        first, second = left.containers
        assert [patch.get_y() for patch in second] == [2.0, -3.0]
        assert left.get_ylim()[0] < -5.0
        assert [patch.get_x() for patch in first] == [patch.get_x() for patch in second]
        assert left.get_ylabel() == "百分点"
        assert all(axis.get_xlabel() == "" for axis in figure.axes)
        assert not any("产量" in line.get_label() for line in left.lines)
        assert [text.get_text() for text in left.get_legend().get_texts()] == list(frame.columns[:2])
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
        "实际GDP当季同比": [3.0, 4.0, 5.0],
        "GDP平减指数同比": [1.0, 2.0, np.nan],
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
    assert lines["实际GDP当季同比"].get_ydata()[-1] == 5.0
    assert np.isnan(lines["GDP平减指数同比"].get_ydata()[-1])
    assert pd.Timestamp(lines["实际GDP当季同比"].get_xdata()[-1]) == pd.Timestamp("2026-06-30")
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
    assert [text.get_text() for text in axis.get_legend().get_texts()] == list(frame.columns)
    assert tuple(figure.get_size_inches()) == (9.4, 6.2)
    assert captured["units"] == {name: "%" for name in frame}
    plt.close(figure)


def test_nonoil_industry_pull_has_only_six_bars_and_two_column_legend():
    industries = ["批发零售", "金融保险", "制造业", "建筑业", "房地产业", "其他行业"]
    frame = pd.DataFrame({name: [2.0, -1.0, 3.0] for name in industries},
                         index=pd.date_range("2025-12-31", periods=3, freq="QE"))
    frame["非油GDP同比"] = frame.sum(axis=1)
    figure = charts.build_nonoil_industry_pull_figure(frame, title="非油行业拉动")
    try:
        assert len(figure.axes) == 1
        axis = figure.axes[0]
        assert axis.get_ylabel() == "百分点"
        assert len(axis.containers) == 6
        assert not any(line.get_label() == "非油GDP同比" for line in axis.lines)
        legend = axis.get_legend()
        assert [item.get_text() for item in legend.get_texts()] == industries
        _apply_cjk_fonts(figure)
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        boxes = [item.get_window_extent(renderer) for item in legend.get_texts()]
        assert len({round(box.x0, 1) for box in boxes}) == 2
        assert len({round(box.y0, 1) for box in boxes}) == 3
        assert [item.get_text() for item in axis.get_xticklabels()] == ["Q4", "Q1", "Q2"]
    finally:
        plt.close(figure)
