from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.government_finance.data import CBUAE_SHEET
from htfa.monitoring.uae.contracts.government_finance.data import CBUAE_INDICATORS


def read_government_finance_data(source: PublishedUAEData):
    """只读取 ``月度_CBUAE`` 的四个目标指标并校验元数据。"""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        values, metadata = parse_target_sheet(
            tables,
            sheet_name=CBUAE_SHEET,
            targets=CBUAE_INDICATORS,
            allowed_frequencies={"月", "月度"},
            expected_unit="百万迪拉姆",
        )
    return (metadata, values)
