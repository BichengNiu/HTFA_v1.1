from __future__ import annotations
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.contracts.oil.data import RIG_COUNT_INDICATOR
from htfa.monitoring.uae.contracts.oil.data import OPEC_PRODUCTION_INDICATOR
from htfa.monitoring.uae.contracts.oil.data import OilMarketData
from htfa.monitoring.uae.data.oil.data import read_oil_market_data


def load_oil_market_data(source: PublishedUAEData) -> OilMarketData:
    """读取当前 EIA、Dubai、OPEC 与 Baker Hughes 工作表。"""
    (
        dubai_metadata,
        price_metadata,
        prices,
        production_frame,
        production_metadata,
        rig_count_frame,
        rig_count_metadata,
    ) = read_oil_market_data(source)
    production = production_frame[OPEC_PRODUCTION_INDICATOR[0]].rename(
        OPEC_PRODUCTION_INDICATOR[0]
    )
    rig_count = rig_count_frame[RIG_COUNT_INDICATOR[0]].rename(RIG_COUNT_INDICATOR[0])
    return OilMarketData(
        prices=prices,
        production=production,
        rig_count=rig_count,
        metadata={
            **price_metadata,
            **dubai_metadata,
            **production_metadata,
            **rig_count_metadata,
        },
    )
