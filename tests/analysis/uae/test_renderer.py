import inspect

import pandas as pd
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest

import dashboard.analysis.uae.renderer as renderer_module
from dashboard.analysis.uae.charts import (
    build_growth_and_sector_pull_figure,
    build_industry_breadth_figure,
    build_industry_concentration_figure,
    build_industry_price_volume_quadrant_figure,
    build_industry_state_matrix_figure,
    build_latest_contribution_figure,
    build_line_figure,
    build_nonoil_industry_pull_figure,
    build_price_volume_figure,
)
from dashboard.analysis.uae.contracts import ProvenanceKind
from dashboard.analysis.uae.renderer import (
    TAB_CONFIG,
    _metric_label,
)
from dashboard.analysis.uae.results import MetricSnapshot


def test_line_chart_contains_visible_series_legend():
    frame = pd.DataFrame(
        {"真实GDP": [1.0, 2.0], "模拟CPI": [3.0, 4.0]},
        index=pd.period_range("2025Q1", periods=2, freq="Q"),
    )

    figure = build_line_figure(frame, title="趋势")

    assert isinstance(figure, go.Figure)
    assert [trace.name for trace in figure.data] == ["真实GDP", "模拟CPI"]


def test_contribution_chart_uses_positive_and_negative_colors():
    frame = pd.DataFrame(
        {"正贡献": [1.2], "负贡献": [-0.4]},
        index=pd.period_range("2025Q4", periods=1, freq="Q"),
    )

    figure = build_latest_contribution_figure(frame, title="贡献")

    assert list(figure.data[0].marker.color) == ["#E15759", "#0B5CAD"]


def test_growth_chart_stacks_sector_pulls_with_oil_production_line():
    frame = pd.DataFrame(
        {
            "【真实】石油及其他液体产量季度同比": [-1.0, 0.5],
            "【真实】非石油经济部门拉动": [1.4, 2.1],
            "【真实】石油经济部门拉动": [-0.4, -0.1],
        },
        index=pd.period_range("2025Q1", periods=2, freq="Q"),
    )

    figure = build_growth_and_sector_pull_figure(
        frame,
        title="GDP部门拉动与石油产量同比",
    )

    assert [trace.type for trace in figure.data] == [
        "bar",
        "bar",
        "scatter",
    ]
    assert figure.data[0].name == "【真实】非石油经济部门拉动"
    assert figure.data[1].name == "【真实】石油经济部门拉动"
    assert figure.data[2].name == "【真实】石油及其他液体产量季度同比"
    assert figure.layout.barmode == "relative"
    assert figure.layout.xaxis.title.text == "季度"
    assert list(figure.layout.xaxis.categoryarray) == ["2025Q1", "2025Q2"]
    assert figure.layout.yaxis.title.text == "同比增速（%）/ 拉动（百分点）"


def test_price_volume_chart_uses_two_lines_on_one_percent_axis():
    frame = pd.DataFrame(
        {
            "【真实】实际GDP当季同比": [2.0, 3.0],
            "【真实】GDP平减指数同比": [2.1, 2.5],
        },
        index=pd.period_range("2025Q3", periods=2, freq="Q"),
    )

    figure = build_price_volume_figure(
        frame,
        title="实际GDP增速与GDP平减指数同比",
    )

    assert [trace.type for trace in figure.data] == ["scatter", "scatter"]
    assert [trace.name for trace in figure.data] == list(frame.columns)
    assert figure.data[0].yaxis == "y"
    assert figure.data[1].yaxis == "y"
    assert figure.layout.xaxis.title.text == "季度"
    assert figure.layout.yaxis.title.text == "同比增速（%）"
    assert "yaxis2" not in figure.layout


def test_nonoil_industry_chart_stacks_quarterly_bars_with_growth_line():
    frame = pd.DataFrame(
        {
            "行业1": [1.0, 0.6],
            "行业2": [0.8, 1.3],
            "行业3": [0.6, 0.7],
            "行业4": [0.4, 0.5],
            "行业5": [0.3, 0.4],
            "其他行业": [0.2, -0.1],
            "【真实】非油GDP同比": [3.3, 3.4],
        },
        index=pd.period_range("2025Q3", periods=2, freq="Q"),
    )

    figure = build_nonoil_industry_pull_figure(
        frame,
        title="非油实际GDP同比及行业拉动",
    )

    assert [trace.type for trace in figure.data] == ["bar"] * 6 + [
        "scatter"
    ]
    assert [trace.name for trace in figure.data] == [
        "行业1",
        "行业2",
        "行业3",
        "行业4",
        "行业5",
        "其他行业",
        "【真实】非油GDP同比",
    ]
    assert figure.data[5].marker.color == "#B8BDC6"
    assert figure.data[-1].name == "【真实】非油GDP同比"
    assert figure.layout.barmode == "relative"
    assert figure.layout.xaxis.title.text == "季度"
    assert figure.layout.xaxis.categoryorder == "array"
    assert list(figure.layout.xaxis.categoryarray) == ["2025Q3", "2025Q4"]


def test_industry_quadrant_chart_has_stable_animation_and_time_badge():
    rows = []
    for quarter, offset in (("2024Q4", 0.0), ("2025Q1", 1.0)):
        for industry, real_growth, price_growth, share in (
            ("制造业", 4.0, -1.0, 0.4),
            ("建筑业", -2.0, 3.0, 0.6),
        ):
            rows.append(
                {
                    "季度": quarter,
                    "行业": industry,
                    "实际增加值增速": real_growth + offset,
                    "行业隐含平减指数增速": price_growth - offset,
                    "实际GDP占非油GDP比例": share,
                }
            )
    frame = pd.DataFrame(rows).set_index(["季度", "行业"])

    figure = build_industry_price_volume_quadrant_figure(
        frame,
        title="行业量价四象限图",
    )

    assert [trace.type for trace in figure.data] == ["scatter", "scatter"]
    assert [trace.name for trace in figure.data] == ["制造业", "建筑业"]
    assert all(trace.marker.sizemode == "area" for trace in figure.data)
    assert len({trace.marker.sizeref for trace in figure.data}) == 1
    assert figure.layout.legend.itemsizing == "constant"
    assert [animation_frame.name for animation_frame in figure.frames] == [
        "2024Q4",
        "2025Q1",
    ]
    assert figure.layout.sliders[0].active == 1
    assert len(figure.layout.sliders[0].steps) == 2
    assert [
        button.label
        for button in figure.layout.updatemenus[0].buttons
    ] == ["▶ 从头播放", "⏸ 暂停"]
    assert figure.layout.xaxis.title.text == "实际增加值同比增速（%）"
    assert figure.layout.yaxis.title.text == "行业隐含平减指数同比增速（%）"
    assert any(
        "2025 Q1" in annotation.text
        for annotation in figure.layout.annotations
    )
    assert any(
        "占比合计：100.0%" in annotation.text
        for annotation in figure.layout.annotations
    )
    assert len(figure.layout.shapes) == 2


def test_industry_quadrant_rejects_non_reconciled_bubble_shares():
    frame = pd.DataFrame(
        {
            "季度": ["2025Q4", "2025Q4"],
            "行业": ["制造业", "建筑业"],
            "实际增加值增速": [4.0, 2.0],
            "行业隐含平减指数增速": [1.0, 3.0],
            "实际GDP占非油GDP比例": [0.4, 0.5],
        }
    ).set_index(["季度", "行业"])

    with pytest.raises(ValueError, match="未加总为1"):
        build_industry_price_volume_quadrant_figure(
            frame,
            title="行业量价四象限图",
        )


def test_industry_breadth_chart_switches_weighting_without_rerun():
    index = pd.period_range("2025Q3", periods=2, freq="Q")
    metrics = (
        "正增长行业比例",
        "增速高于历史均值的行业比例",
        "增速较上季度加快的行业比例",
        "连续四季度正增长的行业比例",
    )
    frame = pd.DataFrame(
        {
            f"{weighting}｜{metric}": [60.0 + position, 70.0 + position]
            for weighting in ("不加权", "加权")
            for position, metric in enumerate(metrics)
        },
        index=index,
    )

    figure = build_industry_breadth_figure(
        frame,
        title="行业扩张广度指数",
    )

    assert [trace.type for trace in figure.data] == ["scatter"] * 8
    assert [trace.visible for trace in figure.data[:4]] == [None] * 4
    assert [trace.visible for trace in figure.data[4:]] == [False] * 4
    assert [
        button.label
        for button in figure.layout.updatemenus[0].buttons
    ] == ["不加权", "按上年同期行业权重加权"]
    assert tuple(figure.layout.yaxis.range) == (0, 100)
    assert {
        float(shape.y0)
        for shape in figure.layout.shapes
        if shape.type == "line"
    } == {50.0, 80.0}


def test_industry_concentration_chart_preserves_boundary_semantics():
    frame = pd.DataFrame(
        {
            "前三行业净增长覆盖率": [150.0, float("nan"), 80.0],
            "正向贡献HHI": [0.4, 0.5, 0.3],
            "正向贡献有效行业数": [2.5, 2.0, 10 / 3],
            "加权增速方差": [9.0, 16.0, 4.0],
            "加权增速标准差": [3.0, 4.0, 2.0],
        },
        index=pd.period_range("2025Q2", periods=3, freq="Q"),
    )

    figure = build_industry_concentration_figure(
        frame,
        title="行业增长集中度",
    )

    assert [trace.type for trace in figure.data] == ["scatter"] * 3
    assert figure.data[0].y[0] == 150.0
    assert figure.data[0].connectgaps is False
    assert figure.data[1].customdata[0][0] == 2.5
    assert figure.layout.yaxis.title.text == "CR3（%）"
    assert figure.layout.yaxis2.title.text == "正向贡献 HHI"
    assert tuple(figure.layout.yaxis2.range) == (0, 1)
    assert figure.layout.yaxis3.title.text == "加权标准差（百分点）"
    assert figure.layout.xaxis3.title.text == "季度"


def test_industry_state_matrix_displays_latest_quarter_and_four_states():
    states = ("高位加速", "高位放缓", "低位改善", "低位恶化")
    frame = pd.DataFrame(
        {
            "季度": ["2025Q4"] * 4,
            "行业": ["制造业", "建筑业", "金融业", "房地产业"],
            "当前实际增加值增速": [8.0, 6.0, 2.0, -1.0],
            "最近4季度平均增速": [7.0, 6.5, 1.0, 0.5],
            "最近8季度平均增速": [6.5, 6.0, 0.8, 1.0],
            "连续正增长季度数": [8, 6, 4, 0],
            "最近8季度高于自身历史趋势次数": [6, 5, 4, 2],
            "当季增速减过去4季度均值": [1.5, -0.5, 1.2, -2.0],
            "当季增速减历史趋势": [1.5, 0.5, -0.5, -2.0],
            "当季增速减上季度增速": [1.0, -1.0, 0.8, -1.5],
            "实际GDP占非油GDP比例": [0.3, 0.25, 0.2, 0.25],
            "行业状态": states,
        }
    ).set_index(["季度", "行业"])

    figure = build_industry_state_matrix_figure(
        frame,
        title="行业增长持续性与状态矩阵",
    )

    assert [trace.name for trace in figure.data] == list(states)
    assert all(trace.marker.sizemode == "area" for trace in figure.data)
    assert all("连续正增长季度数" in trace.hovertemplate for trace in figure.data)
    assert figure.layout.legend.itemsizing == "constant"
    assert figure.layout.xaxis.title.text == "相对自身历史趋势（百分点）"
    assert figure.layout.yaxis.title.text == "较上季度增速变化（百分点）"
    assert len(figure.layout.shapes) == 2
    assert any(
        "2025 Q4" in annotation.text
        for annotation in figure.layout.annotations
    )
    assert {annotation.text.replace("<b>", "").replace("</b>", "")
            for annotation in figure.layout.annotations} >= set(states)


def test_metric_label_never_hides_simulated_provenance():
    metric = MetricSnapshot(
        label="总体CPI同比",
        value=2.0,
        unit="%",
        period="2025-12",
        provenance_kind=ProvenanceKind.SIMULATED,
    )

    assert _metric_label(metric) == "【模拟】总体CPI同比"


def test_renderer_has_six_reading_tabs_and_no_raw_dataframe():
    assert [label for label, _ in TAB_CONFIG] == [
        "宏观概览",
        "行业分析",
        "通货膨胀",
        "就业与收入",
        "财政与外部",
        "货币与金融",
    ]
    source = inspect.getsource(renderer_module)
    assert "诊断结论" not in source
    assert "headline.summary" not in source
    assert "DEFAULT_UAE_WORKBOOK" not in source
    assert ".dataframe(" not in source
    assert ".table(" not in source


def test_page_without_upload_shows_gate_and_no_charts():
    app = AppTest.from_string(
        """
from dashboard.analysis.uae.renderer import render_uae_monitoring
render_uae_monitoring()
"""
    )

    app.run(timeout=90)

    assert len(app.exception) == 0
    assert app.title[0].value == "阿联酋经济监测"
    assert len(app.tabs) == 0
    assert "请先在侧边栏" in app.info[0].value


def test_uploaded_uae_workbook_renders_six_tabs():
    app = AppTest.from_string(
        """
from io import BytesIO
import dashboard.analysis.uae.renderer as renderer
from dashboard.analysis.uae.data_adapter import DEFAULT_UAE_WORKBOOK

uploaded = BytesIO(DEFAULT_UAE_WORKBOOK.read_bytes())
uploaded.name = "uae.xlsx"
renderer._select_data_source = lambda: uploaded
renderer.render_uae_monitoring()
"""
    )

    app.run(timeout=90)

    assert len(app.exception) == 0
    assert len(app.tabs) == 6
    assert [tab.label for tab in app.tabs] == [
        "宏观概览",
        "行业分析",
        "通货膨胀",
        "就业与收入",
        "财政与外部",
        "货币与金融",
    ]
    assert len(app.tabs[0].subheader) == 0
    assert sum(
        type(child).__name__ == "UnknownElement"
        for child in app.tabs[0].children.values()
    ) == 3
    assert sum(
        type(child).__name__ == "UnknownElement"
        for child in app.tabs[1].children.values()
    ) == 6
