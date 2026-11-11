from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.government_finance.rates import RATES_SHEET
from htfa.monitoring.uae.contracts.government_finance.rates import RATES_INDICATORS
from htfa.monitoring.uae.contracts.government_finance.rates import ALLOWED_FREQUENCIES


def read_rates_data(source: PublishedUAEData, *, today: pd.Timestamp | None = None):
    """读取三条原始利率及其频率、单位和来源元数据。"""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        frame, metadata = parse_target_sheet(
            tables,
            sheet_name=RATES_SHEET,
            targets=RATES_INDICATORS,
            allowed_frequencies=ALLOWED_FREQUENCIES,
            expected_unit="%",
        )
    return (frame, metadata)
