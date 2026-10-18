"""Calendar month normalization shared by UAE sources and coverage checks."""

from datetime import date

import pytest

from htfa.data.temporal import calendar_month_end, month_end_from_period


@pytest.mark.parametrize("period, expected", [
    ("2024-02", date(2024, 2, 29)),
    ("2025-02", date(2025, 2, 28)),
    ("2026-04", date(2026, 4, 30)),
    ("2026-12", date(2026, 12, 31)),
])
def test_sources_agree_on_leap_years_and_year_end(period, expected):
    assert month_end_from_period(period) == expected
    assert calendar_month_end(expected.year, expected.month) == expected


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "invalid"])
def test_invalid_source_month_is_rejected(period):
    with pytest.raises(ValueError):
        month_end_from_period(period)
