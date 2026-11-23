"""The official PDF adapter retains the existing secondary-source definition."""

from datetime import date

import pytest

from htfa.monitoring.uae.jobs.source_oil import parse_opec_pdf_text


def test_pdf_uses_monthly_secondary_sources_and_excludes_direct_communication():
    text = """Table 5 - 7: DoC crude oil production based on secondary sources, tb/d
Secondary Change
sources 2024 2025 1Q26 2Q26 3Q26 Jul 26 Aug 26 Sep 26 Sep/Aug
Algeria 905 935 972 983 999 995 1,000 1,003 3
UAE 2,969 3,161 2,898 2,668 3,842 3,780 3,831 3,917 86
Direct communication
UAE 2,916 3,119 2,877 2,644 .. .. .. .. ..
"""
    rows = parse_opec_pdf_text(text, "report.pdf")
    assert [(r.period, r.production_bpd) for r in rows] == [
        (date(2026, 7, 31), 3780000),
        (date(2026, 8, 31), 3831000),
        (date(2026, 9, 30), 3917000),
    ]
    assert all(r.source_file == "report.pdf" for r in rows)


def test_pdf_rejects_missing_or_ambiguous_production_table():
    for text in ["Direct communication UAE 3,000", "based on secondary sources, tb/d"]:
        with pytest.raises(ValueError):
            parse_opec_pdf_text(text, "report.pdf")
