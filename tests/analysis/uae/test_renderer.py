"""Tests for the UAE report page renderer."""

import re
from unittest.mock import MagicMock

import pandas as pd

from htfa.monitoring.uae.renderer import _render_report_header


def test_report_header_places_organization_and_data_month_on_meta_line() -> None:
    st_obj = MagicMock()

    _render_report_header(st_obj, pd.Period("2026-08", freq="M"))

    html = st_obj.markdown.call_args.args[0]
    assert 'class="uae-print-report-meta"' in html
    assert "中国驻阿联酋大使馆、国家发展改革委国家信息中心" in html
    assert re.search(
        r'class="uae-print-report-period">\d{4}年\d{1,2}月</div>',
        html,
    )
    assert "2026年8月" in html
    assert "uae-print-page-number" not in html
