"""Tests for the UAE report page renderer."""

import re
from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd

from tests.analysis.uae._helpers import report_source

from htfa.monitoring.uae.renderer import (
    _latest_high_frequency_month,
    _render_report_header,
)


def _high_frequency_workbook() -> bytes:
    monthly_rows = [
        ["月度测试", None],
        ["指标名称", "测试指标"],
        ["频率", "月度"],
        ["单位", "指数"],
        ["来源", "测试"],
        ["更新时间", "2026-08-31"],
        ["2026-09-01", 1],
        ["2026-08-01", 2],
    ]
    daily_rows = [
        ["日度测试", None],
        ["指标名称", "测试日度指标"],
        ["频率", "日度"],
        ["单位", "指数"],
        ["来源", "测试"],
        ["更新时间", "2026-08-31"],
        ["2026-08-30", 3],
    ]
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame().to_excel(writer, sheet_name="指标字典", index=False)
        pd.DataFrame(monthly_rows).to_excel(
            writer,
            sheet_name="月度_测试",
            header=False,
            index=False,
        )
        pd.DataFrame(daily_rows).to_excel(
            writer,
            sheet_name="日度_测试",
            header=False,
            index=False,
        )
    return output.getvalue()


def test_latest_high_frequency_month_ignores_future_observations() -> None:
    latest = _latest_high_frequency_month(
        (report_source(_high_frequency_workbook()), "uae.duckdb"),
        today=pd.Timestamp("2026-08-31"),
    )

    assert latest == pd.Period("2026-07", freq="M")


def test_report_header_places_organization_and_data_month_on_meta_line() -> None:
    st_obj = MagicMock()

    _render_report_header(st_obj, pd.Period("2026-08", freq="M"))

    html = st_obj.markdown.call_args.args[0]
    assert 'class="uae-print-report-meta"' in html
    assert (
        "中国驻阿联酋大使馆、国家发展改革委国家信息中心"
        in html
    )
    assert re.search(
        r'class="uae-print-report-period">\d{4}年\d{1,2}月</div>',
        html,
    )
    assert "2026年8月" in html
    assert "uae-print-page-number" not in html


def test_macro_data_tab_has_four_charts_without_explanations():
    from streamlit.testing.v1 import AppTest
    from htfa.monitoring.uae.renderer import GROWTH_OVERVIEW_GROUPS, GROWTH_INDUSTRY_GROUPS

    assert GROWTH_OVERVIEW_GROUPS == (
        "实际GDP增速与GDP平减指数同比",
        "GDP部门拉动与石油产量同比",
        "非石油实际GDP增速与非石油GDP平减指数同比",
        "非油实际GDP行业拉动",
    )
    assert "非油实际GDP行业拉动" not in GROWTH_INDUSTRY_GROUPS
    app = AppTest.from_string('''
import streamlit as st
from htfa.monitoring.uae.renderer import render_uae_monitoring
st.session_state["analysis.uae.active_tab"] = "宏观数据"
render_uae_monitoring()
''').run(timeout=90)
    assert not app.exception
    assert not app.error
    assert [tab.label for tab in app.tabs] == ["宏观数据", "行业分析", "高频数据"]
    assert len(app.get("image")) == 4
    assert not app.get("plotly_chart")
    assert not app.expander
    assert len(app.get("column")) == 4


def test_missing_configured_chart_is_not_silently_skipped():
    import pytest
    from htfa.monitoring.uae.renderer import _ordered_series_groups
    with pytest.raises(KeyError, match="required chart"):
        _ordered_series_groups({}, ("required chart",))
