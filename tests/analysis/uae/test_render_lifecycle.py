"""Another Streamlit session must not detach a UAE chart's active canvas."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
import pandas as pd
import pytest
from streamlit.runtime.scriptrunner.script_runner import _clean_problem_modules
from streamlit.testing.v1 import AppTest

from htfa.monitoring.uae import charts
from htfa.monitoring.uae.supplemental_charts import build_supplemental_figure
from htfa.monitoring.uae.supplemental_data import FINANCE_CHARTS
from htfa.ui_shared.chart_legend import render_pyplot_figure


def test_csv_download_does_not_rerun_the_report():
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from htfa.monitoring.uae.downloads import render_chart_download
render_chart_download(st, pd.DataFrame({"GDP": [1, 2]}), title="GDP", key="csv")
''').run()
    assert not app.exception
    assert app.get("download_button")[0].proto.ignore_rerun


@pytest.mark.parametrize("chart", ["gdp", "sector", "industry", "monthly"])
def test_chart_survives_another_session_cleanup_during_layout(monkeypatch, chart):
    index = pd.date_range("2025-03-31", periods=6, freq="QE")
    if chart == "gdp":
        frame = pd.DataFrame({
            "实际GDP当季同比": [3, 4, 5, 3, 2, 1],
            "GDP平减指数同比": [1, 2, 3, 1, 0, -1],
        }, index=index)
        builder = charts.build_price_volume_figure
    elif chart == "sector":
        frame = pd.DataFrame({
            "非石油经济部门拉动": [2, 3, 4, 2, 1, 0],
            "石油经济部门拉动": [1, 1, 1, 1, 1, 1],
            "石油及其他液体产量季度同比": [10, 12, 13, 8, 6, -5],
        }, index=index)
        builder = charts.build_growth_and_sector_pull_figure
    elif chart == "industry":
        frame = pd.DataFrame({
            "制造业": [2, 3, 4, 2, 1, 0],
            "其他行业": [1, 1, 1, 1, 1, 1],
        }, index=index)
        builder = charts.build_nonoil_industry_pull_figure
    else:
        frame = pd.DataFrame({
            "DFM综合股指": [100, 110, 120, 110, 100, 90],
            "FTSE ADX综合股指": [200, 220, 240, 220, 200, 180],
        }, index=pd.date_range("2026-01-31", periods=6, freq="ME"))

        def builder(values, *, title, source_text):
            return build_supplemental_figure(
                values, spec=FINANCE_CHARTS[0],
                units={name: "点" for name in values}, source_text=source_text,
            )

    original_draw = FigureCanvasAgg.draw
    cleaned = False
    # Streamlit closes every pyplot figure when any session finishes a run.
    # Schedule that real cleanup on a different thread during the first draw.
    with ThreadPoolExecutor(max_workers=1) as other_session:
        def draw_during_cleanup(canvas):
            nonlocal cleaned
            if not cleaned:
                cleaned = True
                other_session.submit(_clean_problem_modules).result(timeout=5)
            return original_draw(canvas)

        monkeypatch.setattr(FigureCanvasAgg, "draw", draw_during_cleanup)
        figure = builder(frame, title="报告图", source_text="公开数据")

    assert cleaned
    assert plt.get_fignums() == []
    assert tuple(figure.get_size_inches()) == (9.4, 6.2)
    canvas = figure.canvas
    _clean_problem_modules()
    assert figure.canvas is canvas
    outputs = []

    class StreamlitSink:
        def pyplot(self, rendered, **kwargs):
            output = BytesIO()
            rendered.savefig(output, format="png", dpi=60, bbox_inches=None)
            outputs.append(output.getvalue())
            if kwargs["clear_figure"]:
                rendered.clear()

    render_pyplot_figure(
        StreamlitSink(), figure, place_legend_bottom=False, bbox_inches=None,
    )
    assert outputs[0].startswith(b"\x89PNG\r\n\x1a\n")
