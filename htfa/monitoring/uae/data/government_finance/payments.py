from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.government_finance.payments import PAYMENT_SHEET
from htfa.monitoring.uae.contracts.government_finance.payments import PAYMENT_INDICATORS


def read_payment_data(source: PublishedUAEData):
    """读取 FTS 客户转账和支票清算四个累计指标。"""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        values, metadata = parse_target_sheet(
            tables,
            sheet_name=PAYMENT_SHEET,
            targets=tuple(
                ((label, indicator) for label, indicator, _ in PAYMENT_INDICATORS)
            ),
            allowed_frequencies={"月"},
            expected_unit={label: unit for label, _, unit in PAYMENT_INDICATORS},
        )
    return (metadata, values)
