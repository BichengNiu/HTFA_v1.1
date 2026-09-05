"""Tests for the CBUAE government/GRE monthly-series extractor."""

import sys
from decimal import Decimal
from pathlib import Path

from htfa.jobs.uae_data._excel_helpers import records_latest_first  # noqa: E402
from htfa.jobs.uae_data.source_cbuae import (  # noqa: E402
    Observation,
    _normalize_label,
    select_latest_vintages,
)


def _observation(
    period: str,
    value: str,
    source_period: str,
) -> Observation:
    values = (Decimal(value),) * 4
    return Observation(period, values, source_period, f"{source_period}.xlsx")


def test_normalize_label_handles_gre_parenthesis_spacing() -> None:
    """Both workbook spellings of the GRE credit row should match."""

    assert _normalize_label("Public Sector ( GREs )") == "public sector (gres)"
    assert _normalize_label("Public Sector (GREs)") == "public sector (gres)"


def test_select_latest_vintage_reports_revisions_and_gaps() -> None:
    """Later bulletins win and missing calendar months remain explicit."""

    observations = [
        _observation("2020-01", "1", "2020-01"),
        _observation("2020-01", "2", "2020-03"),
        _observation("2020-03", "3", "2020-03"),
    ]
    selected, missing, revised_periods = select_latest_vintages(
        observations,
        start_period="2020-01",
        end_period="2020-03",
    )

    assert [item.period for item in selected] == ["2020-01", "2020-03"]
    assert selected[0].values[0] == Decimal("2")
    assert missing == ["2020-02"]
    assert revised_periods == 1


def test_excel_records_are_serialized_latest_first() -> None:
    """The managed CBUAE sheet must display the newest month first."""

    records = records_latest_first(
        [
            _observation("2020-01", "1", "2020-01"),
            _observation("2020-03", "3", "2020-03"),
            _observation("2020-02", "2", "2020-02"),
        ]
    )

    assert [record["period"] for record in records] == [
        "2020-03",
        "2020-02",
        "2020-01",
    ]
