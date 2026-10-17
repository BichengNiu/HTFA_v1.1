"""新增图的时间边界、零值语义和报告布局。"""

from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from htfa.monitoring.uae import supplemental_renderer as renderer
from htfa.monitoring.uae.supplemental_data import (
    FINANCE_CHARTS, PRICE_CHARTS, PROPERTY_CHARTS, TRANSPORT_CHARTS,
    load_chart_data,
)


@pytest.fixture
def workbook():
    sheets = {}
    for spec in FINANCE_CHARTS + PROPERTY_CHARTS + TRANSPORT_CHARTS + PRICE_CHARTS:
        columns = sheets.setdefault(spec.sheet, {})
        for label, indicator, unit in spec.series:
            columns[indicator] = (spec.frequency, unit)
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        for sheet, columns in sheets.items():
            rows = [["指标", *range(len(columns))], ["指标名称", *columns],
                    ["频率", *[v[0] for v in columns.values()]],
                    ["单位", *[v[1] for v in columns.values()]],
                    ["来源", *["test source"] * len(columns)],
                    ["更新时间", *["2026-10-15"] * len(columns)]]
            historical = ("2022-01-31",) if sheet == "月度_FCSC" else ()
            for date in (*historical, "2026-08-31", "2026-09-15", "2026-09-30",
                         "2026-10-14", "2026-10-31"):
                values = []
                for indicator in columns:
                    value = 20.0
                    if "合计总量" in indicator:
                        value = 0.0 if date == "2026-08-31" else 100.0
                    if sheet == "日度_Wind" or "经确认新期房" in indicator:
                        value = 0.0 if date == "2026-08-31" else value
                    if sheet == "日度_Wind" and date == "2026-09-15":
                        value = 60.0
                    if sheet == "周度_迪拜房地产" and date == "2026-09-15":
                        value = 10.0
                    if sheet == "日度_Wind" and date.startswith("2026-10"):
                        value = 1000.0
                    values.append(value)
                rows.append([pd.Timestamp(date), *values])
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False, header=False)
    return stream.getvalue()


def test_monthly_excludes_partial_month_and_transit_share_handles_zero(workbook):
    values, _, units = load_chart_data(
        workbook, "test.xlsx", TRANSPORT_CHARTS[2], today=pd.Timestamp("2026-10-15"),
    )
    assert values.index.max() == pd.Timestamp("2026-09-30")
    assert pd.isna(values.loc["2026-08-31", "转运占比"])
    assert values.loc["2026-09-30", "转运占比"] == pytest.approx(20.0)
    assert units == {"转运量": "吨", "转运占比": "%"}


def test_federal_cpi_monthly_chart_uses_index_and_complete_months(workbook):
    values, metadata, units = load_chart_data(
        workbook, "test.xlsx", PRICE_CHARTS[1], today=pd.Timestamp("2026-10-15"),
    )
    assert values.index.min() == pd.Timestamp("2022-01-31")
    assert values.index.max() == pd.Timestamp("2026-09-30")
    assert values.columns.tolist() == ["总体 CPI 同比", "食品与饮料 CPI 同比"]
    assert units == {"总体 CPI 同比": "%", "食品与饮料 CPI 同比": "%"}
    assert set(metadata) == {"总体 CPI 同比", "食品与饮料 CPI 同比"}


def test_daily_and_weekly_monthly_means_preserve_valid_weekly_zero(workbook):
    daily, _, _ = load_chart_data(
        workbook, "test.xlsx", FINANCE_CHARTS[0], today=pd.Timestamp("2026-10-15"),
    )
    weekly, _, _ = load_chart_data(
        workbook, "test.xlsx", PROPERTY_CHARTS[0], today=pd.Timestamp("2026-10-15"),
    )
    assert list(daily.index) == [pd.Timestamp("2026-09-30")]
    assert len(daily.columns) == 2
    assert daily.iloc[0].tolist() == [40.0, 40.0]
    fx, _, _ = load_chart_data(
        workbook, "test.xlsx", FINANCE_CHARTS[1], today=pd.Timestamp("2026-10-15"),
    )
    assert fx.iloc[0, 0] == 40.0
    assert weekly.loc["2026-08-31"].iloc[0] == 0
    assert weekly.loc["2026-09-30"].tolist() == [15.0, 15.0]
    assert weekly.index.max() == pd.Timestamp("2026-09-30")
    assert weekly.index.is_month_end.all()
    assert weekly.index.to_period("M").is_unique


def test_failed_extra_chart_does_not_hide_sibling_or_create_subsection(monkeypatch):
    values = pd.DataFrame({"value": [1]}, index=pd.to_datetime(["2026-09-30"]))

    def load(content, name, spec):
        if spec.key == "dfm":
            raise ValueError("missing source")
        return values, {}, {"value": "AED/CNY"}

    monkeypatch.setattr(renderer, "load_chart_data", load)
    monkeypatch.setattr(renderer, "build_supplemental_figure", lambda *a, **k: object())
    monkeypatch.setattr(renderer, "render_pyplot_figure", lambda *a, **k: None)
    monkeypatch.setattr(renderer, "render_chart_download", lambda *a, **k: None)
    st_obj = MagicMock()
    st_obj.columns.return_value = (MagicMock(), MagicMock())
    result = renderer.render_supplemental_charts(st_obj, b"", "test.xlsx", FINANCE_CHARTS)
    assert result == {"cny_aed": "2026-09-30"}
    st_obj.warning.assert_called_once()
    st_obj.subheader.assert_not_called()
    st_obj.expander.assert_not_called()
    for cell in st_obj.columns.return_value:
        cell.caption.assert_not_called()


def test_new_charts_render_in_app_without_subsections():
    app = AppTest.from_string('''
import streamlit as st
from htfa.monitoring.uae.database import published_source
from htfa.monitoring.uae.supplemental_data import FINANCE_CHARTS, PROPERTY_CHARTS, TRANSPORT_CHARTS
from htfa.monitoring.uae.supplemental_renderer import render_supplemental_charts, render_prices_section
p = published_source()
for specs in (FINANCE_CHARTS, PROPERTY_CHARTS, TRANSPORT_CHARTS):
    render_supplemental_charts(st, p, p.name, specs)
render_prices_section(st, (p, p.name))
''').run(timeout=60)
    assert not app.exception
    assert not app.warning
    assert [element.value for element in app.subheader] == ["物价"]
    assert not app.caption
    assert [metric.label for metric in app.metric] == [
        "螺纹钢报价", "钢坯及方坯报价", "3mm热轧卷报价",
        "总体 CPI 同比", "食品与饮料 CPI 同比",
    ]
    assert all(metric.value.endswith("美元/吨") for metric in app.metric[:3])
    assert all(metric.value.endswith("%") for metric in app.metric[3:])
    assert all(metric.delta.endswith("个百分点") for metric in app.metric[3:])


def test_price_cpi_metrics_show_changes_in_percentage_points():
    spec = PRICE_CHARTS[1]
    values = pd.DataFrame(
        {"总体 CPI 同比": [2.0, 3.0], "食品与饮料 CPI 同比": [-1.0, -0.5]},
        index=pd.to_datetime(["2026-05-31", "2026-06-30"]),
    )
    st_obj = MagicMock()
    renderer._render_price_metrics(st_obj, [(spec, values, {}, {})])

    calls = st_obj.metric.call_args_list
    assert [call.args for call in calls] == [
        ("总体 CPI 同比", "3.00%"),
        ("食品与饮料 CPI 同比", "-0.50%"),
    ]
    assert [call.kwargs["delta"] for call in calls] == [
        "较上月 +1.00 个百分点", "较上月 +0.50 个百分点",
    ]
    st_obj.container.assert_called_once_with(
        horizontal=True, horizontal_alignment="left",
    )
    assert all(call.kwargs["width"] == 300 for call in calls)
    st_obj.caption.assert_not_called()


def test_real_estate_renders_five_charts_without_extra_captions():
    app = AppTest.from_string('''
import streamlit as st
from htfa.monitoring.uae.database import published_source
from htfa.monitoring.uae.real_estate.renderer import render_real_estate_section
p = published_source()
render_real_estate_section(st, p, p.name)
''').run(timeout=60)
    assert not app.exception
    assert not app.warning
    assert not app.error
    assert len(app.get("image")) == 5
    assert len(app.get("download_button")) == 5
    assert [element.value for element in app.subheader] == ["房地产"]
    assert not app.caption
