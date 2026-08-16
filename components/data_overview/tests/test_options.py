"""选项构建层测试：UI 状态 ↔ Ts plot_series 参数一致性 + 前缀隔离。"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest
from Ts.TsPlots import plot_series

from data_overview.core.dataset import build_overview_dataset
from data_overview.core.options import (
    build_chart_options,
    build_table_options,
)

# build_chart_options 输出中固定由 UI 层调用时另行传入的键。
_FIXED_AT_CALL_SITE = {
    "auto_dual_y",
}

# UI 层键名 → Ts plot_series 参数名的别名（draw_series_plot 内转换）。
_UI_TO_TS_ALIASES = {
    "line_width": "linewidth",
    "marker_size": "markersize",
}


def _dataset():
    return build_overview_dataset(
        pd.DataFrame(
            {
                "date": pd.date_range("2020-01-01", periods=30, freq="MS"),
                "a": range(30),
                "b": range(30, 60),
            }
        ),
        "sample.csv",
        "fp",
    )


def _state(**overrides):
    state = {}
    state.update(overrides)
    return state


def test_chart_options_keys_match_plot_series_signature():
    """build_chart_options 输出键（别名映射后）⊆ plot_series 参数。"""
    dataset = _dataset()
    options, errors = build_chart_options(_state(), dataset, dataset.frame)
    assert errors == []
    signature = set(inspect.signature(plot_series).parameters)
    mapped = {_UI_TO_TS_ALIASES.get(key, key) for key in options}
    assert mapped | _FIXED_AT_CALL_SITE <= signature
    # 覆盖度：UI 可驱动的绘图参数都应被构建。
    assert set(options) >= {
        "title",
        "xtitle",
        "ytitle",
        "ymin",
        "xmin",
        "ytick_count",
        "ylabel_count",
        "xtick_count",
        "xlabel_count",
        "line_width",
        "marker_size",
        "marker_edge_width",
        "year_ruler",
        "grid",
        "grid_axis",
        "grid_linewidth",
        "grid_linestyle",
        "show_legend",
        "legend_loc",
        "legend_title",
        "legend_cols",
        "title_loc",
        "title_position",
        "xtitle_loc",
        "ytitle_position",
        "note",
        "note_loc",
        "note_prefix",
        "show_values",
        "value_decimals",
        "facet",
        "facet_rows",
        "facet_cols",
        "figsize",
        "sharey",
        "second_axis_vars",
        "third_axis_vars",
        "second_axis_title",
        "third_axis_title",
        "log_vars",
        "vlines",
        "vline_color",
        "vline_linestyle",
        "shade",
        "shade_color",
        "shade_alpha",
    }


def test_chart_options_defaults():
    """未设置任何控件时的默认参数与控件默认值一致。"""
    dataset = _dataset()
    options, errors = build_chart_options(_state(), dataset, dataset.frame)
    assert errors == []
    assert options["figsize"] == (12.8, 7.2)
    assert options["title"] is None
    assert options["xtitle"] == ""
    assert options["note_prefix"] == "数据来源："
    assert options["grid"] is True
    assert options["grid_axis"] == "both"
    assert options["legend_loc"] == "best"
    assert options["title_loc"] == "center"
    assert options["title_position"] == "top"
    assert options["facet"] is False
    assert options["second_axis_vars"] == []
    assert options["third_axis_vars"] == []
    assert options["vline_color"] == "#d9534f"
    assert options["shade_color"] == "#999999"


def test_chart_options_chinese_mapping_roundtrip():
    """中文选项 → 枚举映射与控件默认一致。"""
    dataset = _dataset()
    options, _ = build_chart_options(
        _state(
            sarimax_preview_title_pos="右上",
            sarimax_preview_xtitle_loc="左",
            sarimax_preview_ytitle_pos="侧边",
            sarimax_preview_note_loc="右",
            sarimax_preview_note_prefix="",
            sarimax_preview_grid_style="纵网格",
            sarimax_preview_vline_color="蓝",
            sarimax_preview_shade_color="绿",
        ),
        dataset,
        dataset.frame,
    )
    assert options["title_loc"] == "right"
    assert options["title_position"] == "top"
    assert options["xtitle_loc"] == "left"
    assert options["ytitle_position"] == "side"
    assert options["note_loc"] == "right"
    assert options["note_prefix"] is None
    assert options["grid"] is True
    assert options["grid_axis"] == "x"
    assert options["vline_color"] == "#3498db"
    assert options["shade_color"] == "#2ecc71"


def test_chart_options_axis_gating():
    """第二/三纵轴变量按开关门控；勾选后才取值。"""
    dataset = _dataset()
    options, _ = build_chart_options(
        _state(
            sarimax_preview_second_axis=["a"],
            sarimax_preview_third_axis=["b"],
            sarimax_preview_second_axis_on=True,
        ),
        dataset,
        dataset.frame,
    )
    assert options["second_axis_vars"] == ["a"]
    assert options["third_axis_vars"] == []


def test_chart_options_vlines_shade_errors():
    """参考线/阴影解析错误汇总返回。"""
    dataset = _dataset()
    options, errors = build_chart_options(
        _state(
            sarimax_preview_vlines="2020-01-01,2021-01-01",
            sarimax_preview_shade="5,3",
        ),
        dataset,
        dataset.frame,
    )
    assert options["vlines"] is not None
    assert len(options["vlines"]) == 2
    assert any("起点不能大于终点" in error for error in errors)


def test_chart_options_xmin_parse():
    """X 轴起点：时间轴按日期解析，非法输入报错。"""
    dataset = _dataset()
    options, errors = build_chart_options(
        _state(sarimax_preview_xmin="2020-03-01"),
        dataset,
        dataset.frame,
    )
    assert options["xmin"] is not None
    assert errors == []

    options, errors = build_chart_options(
        _state(sarimax_preview_xmin="不是日期"),
        dataset,
        dataset.frame,
    )
    assert options["xmin"] is None
    assert any("X 轴起点无法解析为日期" in error for error in errors)


def test_table_options_defaults_and_filter():
    """表格选项：默认全量 + head；数值筛选与时间筛选生效。"""
    dataset = _dataset()
    table = build_table_options(_state(), dataset)
    assert table["mask"].all()
    assert table["view"] == "head"

    table = build_table_options(
        _state(
            sarimax_table_filter_col="a",
            sarimax_table_filter_op="≥",
            sarimax_table_filter_val=15.0,
        ),
        dataset,
    )
    assert table["mask"].sum() == 15
    assert table["view"] == "head"

    table = build_table_options(
        _state(sarimax_table_view_head=False, sarimax_table_view_tail=True),
        dataset,
    )
    assert table["view"] == "tail"


def test_key_prefix_isolation():
    """不同 key_prefix 读取完全隔离的键。"""
    dataset = _dataset()
    options, errors = build_chart_options(
        _state(dfm_preview_title="标题", dfm_preview_grid_style="横网格"),
        dataset,
        dataset.frame,
        key_prefix="dfm",
    )
    assert errors == []
    assert options["title"] == "标题"
    assert options["grid_axis"] == "y"
    # 默认前缀不受 dfm 键影响。
    options2, _ = build_chart_options(_state(), dataset, dataset.frame)
    assert options2["title"] is None
    assert options2["grid_axis"] == "both"


def test_widget_key_generation():
    """键生成函数与历史默认一致；不同前缀无交集。"""
    from data_overview.ui.widget_keys import (
        chart_widget_keys,
        overview_widget_keys,
        preview_key,
        selector_widget_keys,
        table_key,
        table_widget_keys,
    )

    assert selector_widget_keys() == ("sarimax_preview_vars",)
    assert "sarimax_preview_title" in chart_widget_keys()
    assert "sarimax_table_filter_col" in table_widget_keys()
    assert overview_widget_keys()[0] == "sarimax_preview_vars"
    assert preview_key("dfm", "title") == "dfm_preview_title"
    assert table_key("dfm", "filter_col") == "dfm_table_filter_col"
    assert not set(overview_widget_keys("sarimax")) & set(
        overview_widget_keys("dfm")
    )
    assert len(overview_widget_keys()) == len(set(overview_widget_keys()))
