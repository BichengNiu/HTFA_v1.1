from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.oil.data import EIA_DAILY_SHEET
from htfa.monitoring.uae.contracts.oil.data import OPEC_MONTHLY_SHEET
from htfa.monitoring.uae.contracts.oil.data import DUBAI_MONTHLY_SHEET
from htfa.monitoring.uae.contracts.oil.data import RIG_COUNT_SHEET
from htfa.monitoring.uae.contracts.oil.data import RIG_COUNT_INDICATOR
from htfa.monitoring.uae.contracts.oil.data import EIA_PRICE_INDICATORS
from htfa.monitoring.uae.contracts.oil.data import DUBAI_PRICE_INDICATOR
from htfa.monitoring.uae.contracts.oil.data import OPEC_PRODUCTION_INDICATOR


def read_oil_market_data(source: PublishedUAEData):
    """读取当前 EIA、Dubai、OPEC 与 Baker Hughes 工作表。"""
    source = require_published_source(source)
    with open_published_tables(source) as tables:
        prices, price_metadata = parse_target_sheet(
            tables,
            sheet_name=EIA_DAILY_SHEET,
            targets=EIA_PRICE_INDICATORS,
            allowed_frequencies={"日度"},
            expected_unit="美元/桶",
        )
        dubai_prices, dubai_metadata = parse_target_sheet(
            tables,
            sheet_name=DUBAI_MONTHLY_SHEET,
            targets=(DUBAI_PRICE_INDICATOR,),
            allowed_frequencies={"月度"},
            expected_unit="美元/桶",
        )
        prices = prices.join(dubai_prices, how="outer")
        production_frame, production_metadata = parse_target_sheet(
            tables,
            sheet_name=OPEC_MONTHLY_SHEET,
            targets=(OPEC_PRODUCTION_INDICATOR,),
            allowed_frequencies={"月度"},
            expected_unit="桶/天",
        )
        rig_count_frame, rig_count_metadata = parse_target_sheet(
            tables,
            sheet_name=RIG_COUNT_SHEET,
            targets=(RIG_COUNT_INDICATOR,),
            allowed_frequencies={"月"},
            expected_unit="台",
        )
    return (
        dubai_metadata,
        price_metadata,
        prices,
        production_frame,
        production_metadata,
        rig_count_frame,
        rig_count_metadata,
    )
