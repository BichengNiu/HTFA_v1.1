"""Annual chart selection and published-table UI workflow."""

from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from htfa.monitoring.uae.annual import (
    ANNUAL_CHARTS, build_annual_figure, capital_formation_values,
    displayed_annual_values, load_annual_data,
)
from tests.analysis.uae._helpers import report_source


def annual_source():
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, _, _ in ANNUAL_CHARTS:
            labels = ["资本形成总额（现价）", "资本形成总额（2010年不变价）"] if sheet == "年度_资本形成" else ["甲", "乙"]
            pd.DataFrame([
                [sheet, None, None], ["指标名称", *[sheet + ":" + label for label in labels]],
                ["频率", "年", "年"], ["单位", "十亿迪拉姆", "十亿迪拉姆"],
                ["来源", "FCSC", "FCSC"], ["更新时间", "2026-10-25", "2026-10-25"],
                ["2015-12-31", 1, None], ["2016-12-31", 2, 3],
            ]).to_excel(writer, sheet_name=sheet, header=False, index=False)
    return report_source(output.getvalue())


def test_published_annual_reader_retains_years_and_missing_observations():
    frames = load_annual_data(annual_source())
    assert len(frames) == 5
    frame = frames["年度_行业资本形成"]
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


def test_capital_growth_uses_current_prices_and_exact_previous_year():
    frame = pd.DataFrame({
        "资本形成总额（现价）": [100, 125, 200, 0, 20],
        "资本形成总额（2010年不变价）": [80, 90, 100, 110, 120],
    }, index=pd.to_datetime(["2010-12-31", "2011-12-31", "2013-12-31", "2014-12-31", "2015-12-31"]))
    values = capital_formation_values(frame, total=True)
    assert list(values) == ["资本形成总额（现价）", "资本形成总额（现价）同比"]
    np.testing.assert_allclose(values.iloc[:, 1], [np.nan, 25, np.nan, -100, np.nan], equal_nan=True)


def test_capital_chart_pairs_absolute_bars_and_percent_lines():
    frame = pd.DataFrame({"资本形成总额（现价）": [100, 125]},
                         index=pd.to_datetime(["2010-12-31", "2011-12-31"]))
    values = capital_formation_values(frame, total=True)
    figure = build_annual_figure(values, title="资本形成", growth=True)
    try:
        left, right = figure.axes
        assert left.get_ylabel() == "十亿迪拉姆"
        assert right.get_ylabel() == "%"
        np.testing.assert_allclose([patch.get_height() for patch in left.containers[0]], [100, 125])
        np.testing.assert_allclose(right.lines[0].get_ydata(), [np.nan, 25], equal_nan=True)
    finally:
        plt.close(figure)


def test_capital_download_contains_all_industry_levels_and_growth(monkeypatch):
    from unittest.mock import MagicMock
    from htfa.monitoring.uae import annual

    frames = load_annual_data(annual_source())
    capture = MagicMock()
    monkeypatch.setattr(annual, "render_chart_download", capture)
    monkeypatch.setattr(annual, "render_pyplot_figure", MagicMock())
    host = MagicMock()
    host.columns.return_value = [MagicMock(), MagicMock()]
    annual.render_annual_data(host, frames)
    total = capture.call_args_list[0].args[1]
    assert not any("不变价" in column for column in total)
    assert total.iloc[1, 1] == 100
    industry = capture.call_args_list[1].args[1]
    assert list(industry.columns) == ["甲", "乙", "甲同比", "乙同比"]
    assert np.isnan(industry.loc[pd.Timestamp("2016-12-31"), "乙同比"])
