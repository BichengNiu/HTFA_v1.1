from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.preview.data.economic_workbook.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.government_finance.credit import CBUAE_SHEET


def read_cbuae_series(
    source: PublishedUAEData, *, targets: tuple[tuple[str, str], ...]
):
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        frame, metadata = parse_target_sheet(
            tables,
            sheet_name=CBUAE_SHEET,
            targets=targets,
            allowed_frequencies={"月", "月度"},
            expected_unit="百万迪拉姆",
        )
    return (frame, metadata)
