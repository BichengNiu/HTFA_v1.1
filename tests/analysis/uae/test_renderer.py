"""Tests for the UAE report page renderer."""

import re
from unittest.mock import MagicMock

from htfa.monitoring.uae.renderer import _render_report_header


def test_report_header_places_organization_and_datetime_on_meta_line() -> None:
    st_obj = MagicMock()

    _render_report_header(st_obj)

    html = st_obj.markdown.call_args.args[0]
    assert 'class="uae-print-report-meta"' in html
    assert (
        "中国驻阿联酋大使馆、国家发展改革委国家信息中心"
        in html
    )
    assert re.search(
        r'class="uae-print-report-period">\d{4}年\d{2}月\d{2}日</div>',
        html,
    )
