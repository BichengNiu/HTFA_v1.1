"""Annual chart selection and published-table UI workflow."""

from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from htfa.monitoring.uae.annual import (
    ANNUAL_CHARTS, build_annual_figure, displayed_annual_values, load_annual_data,
)
from tests.analysis.uae._helpers import report_source


def annual_source():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, _, _ in ANNUAL_CHARTS:
            pd.DataFrame([
                [sheet, None, None], ["指标名称", sheet + ":甲", sheet + ":乙"],
                ["频率", "年", "年"], ["单位", "十亿迪拉姆", "十亿迪拉姆"],
                ["来源", "FCSC", "FCSC"], ["更新时间", "2026-10-25", "2026-10-25"],
                ["2015-12-31", 1, None], ["2016-12-31", 2, 3],
            ]).to_excel(writer, sheet_name=sheet, header=False, index=False)
    return report_source(output.getvalue())


def test_published_annual_reader_retains_years_and_missing_observations():
    frames = load_annual_data(annual_source())
    assert len(frames) == 5
    frame = next(iter(frames.values()))
    assert list(frame.index.year) == [2015, 2016]
    assert list(frame.columns) == ["甲", "乙"]
    assert np.isnan(frame.iloc[0, 1])


def test_top_industries_use_fixed_latest_year_ranking_without_zero_filling():
    frame = pd.DataFrame({str(i): [10 - i, i] for i in range(7)},
                         index=pd.to_datetime(["2015-12-31", "2016-12-31"]))
    frame.iloc[0, 6] = np.nan
    display = displayed_annual_values(frame, True)
    assert list(display.columns) == ["6", "5", "4", "3", "2"]
    assert np.isnan(display.iloc[0, 0])


def test_annual_figure_uses_single_axis_and_report_style():
    frame = next(iter(load_annual_data(annual_source()).values()))
    figure = build_annual_figure(frame, title="年度投资", bars=True)
    try:
        assert len(figure.axes) == 1
        assert figure.axes[0].get_ylabel() == "十亿迪拉姆"
        assert len(figure.axes[0].containers) == 2
        assert set(figure.axes[0].get_xticks()).issubset(set(frame.index.year))
        assert all(label.get_text().isdigit() for label in figure.axes[0].get_xticklabels())
    finally:
        plt.close(figure)


def test_annual_tab_renders_all_charts_and_downloads():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string('''
import streamlit as st
from tests.analysis.uae.test_annual import annual_source
from htfa.monitoring.uae import renderer
from unittest.mock import patch
st.session_state["analysis.uae.active_tab"] = "年度数据"
with patch.object(renderer, "published_source", annual_source), patch.object(renderer, "_latest_high_frequency_month", lambda source: None):
    renderer.render_uae_monitoring()
''').run(timeout=90)
    assert not app.exception
    assert not app.error
    assert [tab.label for tab in app.tabs] == ["年度数据", "季度数据", "行业分析", "月度数据"]
    assert len(app.get("image")) == 5
    assert len(app.get("download_button")) == 5
