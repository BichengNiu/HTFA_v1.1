from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.foreign_labor import FOREIGN_LABOR_SHEET
from htfa.monitoring.uae.contracts.foreign_labor import SERIES_SPECS


def read_foreign_labor_data(source: PublishedUAEData):
    """Read the two official labour-flow series from the foreign-labour sheet."""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        values, metadata = parse_target_sheet(
            tables,
            sheet_name=FOREIGN_LABOR_SHEET,
            targets=tuple(((name, name) for name, _ in SERIES_SPECS)),
            allowed_frequencies={"月"},
            expected_unit="人",
        )
    return (metadata, values)
