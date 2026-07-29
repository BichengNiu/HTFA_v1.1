import inspect

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

from dashboard.analysis.uae.charts import (
    build_latest_contribution_figure,
    build_line_figure,
)
from dashboard.analysis.uae.renderer import (
    TAB_CONFIG,
    _metric_label,
)
from dashboard.analysis.uae.results import MetricSnapshot
from dashboard.analysis.uae.contracts import ProvenanceKind
import dashboard.analysis.uae.renderer as renderer_module


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
        "总览",
        "增长与结构",
        "通货膨胀",
        "就业与收入",
        "财政与外部",
        "货币与金融",
    ]
    source = inspect.getsource(renderer_module)
    assert ".dataframe(" not in source
    assert ".table(" not in source


def test_default_streamlit_page_renders_without_exception():
    app = AppTest.from_string(
        """
from dashboard.analysis.uae.renderer import render_uae_monitoring
render_uae_monitoring()
"""
    )

    app.run(timeout=90)

    assert len(app.exception) == 0
    assert app.title[0].value == "阿联酋经济监测"
    assert len(app.tabs) == 6
