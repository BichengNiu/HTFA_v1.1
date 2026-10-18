"""阿联酋 V2 油价与原油产量的DuckDB 报告适配器。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from htfa.monitoring.uae.database import PublishedUAEData, require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.data.economic_workbook import SheetSeriesMetadata


EIA_DAILY_SHEET = "日度_EIA"
OPEC_MONTHLY_SHEET = "月度_OPEC"
DUBAI_MONTHLY_SHEET = "月度_Dubai"
RIG_COUNT_SHEET = "月度_贝克休斯"

RIG_COUNT_INDICATOR = ("阿联酋石油活跃钻机数", "阿联酋石油活跃钻机数")
EIA_PRICE_INDICATORS = (("布伦特现货", "布伦特现货"),)
DUBAI_PRICE_INDICATOR = ("迪拜现货", "全球: 名义商品价格: 迪拜原油")
OPEC_PRODUCTION_INDICATOR = ("阿联酋原油产量", "阿联酋原油产量")


@dataclass(frozen=True)
class OilMarketData:
    """油价与产量监测所需的最小数据集。"""

    prices: pd.DataFrame
    production: pd.Series
    rig_count: pd.Series
    metadata: dict[str, SheetSeriesMetadata]


def load_oil_market_data(
    source: PublishedUAEData,
) -> OilMarketData:
    """读取当前 EIA、Dubai、OPEC 与 Baker Hughes 工作表。"""

    source = require_published_source(source)
    with source.open() as tables:
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

    production = production_frame[OPEC_PRODUCTION_INDICATOR[0]].rename(
        OPEC_PRODUCTION_INDICATOR[0]
    )
    rig_count = rig_count_frame[RIG_COUNT_INDICATOR[0]].rename(
        RIG_COUNT_INDICATOR[0]
    )
    required_series = {
        **{name: prices[name] for name, _ in EIA_PRICE_INDICATORS},
        DUBAI_PRICE_INDICATOR[0]: prices[DUBAI_PRICE_INDICATOR[0]],
        OPEC_PRODUCTION_INDICATOR[0]: production,
        RIG_COUNT_INDICATOR[0]: rig_count,
    }
    empty = [
        name for name, series in required_series.items()
        if series.dropna().empty
    ]
    if empty:
        raise ValueError(f"石油监测数据库缺少有效观测：{empty}")

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


__all__ = [
    "OilMarketData",
    "EIA_DAILY_SHEET",
    "OPEC_MONTHLY_SHEET",
    "DUBAI_MONTHLY_SHEET",
    "EIA_PRICE_INDICATORS",
    "DUBAI_PRICE_INDICATOR",
    "OPEC_PRODUCTION_INDICATOR",
    "RIG_COUNT_INDICATOR",
    "RIG_COUNT_SHEET",
    "load_oil_market_data",
]
