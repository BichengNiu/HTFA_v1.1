"""页面级分面编排参数的回归测试。"""

from __future__ import annotations

from data_overview.ui.section import _page_facet_chart_options


def test_page_facet_supplies_default_legend_and_removes_inapplicable_axes():
    """独立分面必须显示变量名，并清除共享/多纵轴参数。"""
    options = {
        "show_legend": True,
        "legend_labels": None,
        "colors": ["#111111", "#222222"],
        "series_styles": None,
        "units": None,
        "log_vars": ["b"],
        "sharex": True,
        "sharey": True,
        "auto_dual_y": True,
        "axis_groups": {"a": "left", "b": "right"},
        "second_axis_vars": ["b"],
        "third_axis_vars": None,
        "second_axis_title": "右轴",
        "third_axis_title": "右轴2",
    }

    chart_options = _page_facet_chart_options(options, ["a", "b"], "b")

    assert chart_options["legend_labels"] == ["b"]
    assert chart_options["facet"] is False
    assert chart_options["sharex"] is False
    assert chart_options["sharey"] is False
    assert chart_options["auto_dual_y"] is False
    assert chart_options["axis_groups"] is None
    assert chart_options["max_y_axes"] == 1
    assert chart_options["second_axis_vars"] is None
    assert chart_options["third_axis_vars"] is None
    assert chart_options["second_axis_title"] is None
    assert chart_options["third_axis_title"] is None
    assert chart_options["legend_bbox"] is None
    assert chart_options["legend_cols"] == 1
    assert chart_options["log_vars"] == ["b"]


def test_page_facet_can_hide_the_automatically_supplied_legend():
    """关闭图例时页面级分面不应重新创建变量名图例。"""
    options = {
        "show_legend": False,
        "legend_labels": None,
        "colors": None,
        "series_styles": None,
        "units": None,
        "log_vars": [],
    }

    chart_options = _page_facet_chart_options(options, ["a"], "a")

    assert chart_options["legend_labels"] is None
