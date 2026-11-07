from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.government_finance.ded import DED_SHEET
from htfa.monitoring.uae.contracts.government_finance.ded import DED_INDICATORS
from htfa.monitoring.uae.contracts.government_finance.ded import EXPECTED_UNITS


def read_ded_data(source: PublishedUAEData):
    """读取 ``月度_DED`` 的有发证活动企业数与当月新发执照数两列。"""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        frame, metadata = parse_target_sheet(
            tables,
            sheet_name=DED_SHEET,
            targets=DED_INDICATORS,
            allowed_frequencies={"月"},
            expected_unit=EXPECTED_UNITS,
            strict_duplicates=True,
        )
    return (frame, metadata)
