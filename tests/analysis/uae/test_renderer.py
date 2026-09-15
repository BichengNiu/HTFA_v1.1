"""Tests for the UAE report page renderer."""

import re
from io import BytesIO
from unittest.mock import MagicMock

import pandas as pd

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
        (_high_frequency_workbook(), "测试.xlsx"),
        today=pd.Timestamp("2026-08-31"),
    )

    assert latest == pd.Period("2026-08", freq="M")


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
