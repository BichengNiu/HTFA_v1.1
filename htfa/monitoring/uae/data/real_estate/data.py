from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.real_estate.data import DLD_SHEET
from htfa.monitoring.uae.contracts.real_estate.data import SALES_COLUMNS


def read_real_estate_data(source: PublishedUAEData):
    """读取并校验 ``月度_DLD`` 的 8 个原始销售列及元数据。"""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        raw_values, raw_metadata = parse_target_sheet(
            tables,
            sheet_name=DLD_SHEET,
            targets=tuple(
                ((label, indicator) for label, indicator, _ in SALES_COLUMNS)
            ),
            allowed_frequencies={"月"},
            expected_unit={label: unit for label, _, unit in SALES_COLUMNS},
            strict_duplicates=True,
        )
    return (raw_metadata, raw_values)
