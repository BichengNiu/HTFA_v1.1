from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.oil.war_pressure import WAM_SHEET
from htfa.monitoring.uae.contracts.oil.war_pressure import OBSERVATION_DAYS_LABEL
from htfa.monitoring.uae.contracts.oil.war_pressure import OBSERVATION_DAYS_INDICATOR
from htfa.monitoring.uae.contracts.oil.war_pressure import WAM_INDICATORS


def read_war_pressure_data(source: PublishedUAEData):
    """读取 WAM 军事打击及观测天数序列。"""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        specifications = (
            *WAM_INDICATORS,
            (OBSERVATION_DAYS_LABEL, OBSERVATION_DAYS_INDICATOR, "天"),
        )
        frame, metadata = parse_target_sheet(
            tables,
            sheet_name=WAM_SHEET,
            targets=tuple(
                ((label, indicator) for label, indicator, _ in specifications)
            ),
            allowed_frequencies={"月"},
            expected_unit={label: unit for label, _, unit in specifications},
            zero_is_missing=False,
        )
    return (frame, metadata)
