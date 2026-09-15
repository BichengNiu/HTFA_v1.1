"""阿联酋 V2 油价与原油产量的窄范围工作簿适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from htfa.data.economic_workbook import (
    EconomicWorkbookReader,
    SheetSeriesMetadata,
)


DAILY_SHEET = "日度_Wind"
MONTHLY_SHEET = "月度_Wind"
EIA_DAILY_SHEET = "日度_EIA"
OPEC_MONTHLY_SHEET = "月度_OPEC"
DUBAI_MONTHLY_SHEET = "月度_Dubai"
RIG_COUNT_SHEET = "月度_贝克休斯"

PRICE_INDICATORS: tuple[tuple[str, str], ...] = (
    ("布伦特期货", "期货结算价(连续): 布伦特原油"),
    ("布伦特现货", "全球: 现货价: 原油(英国布伦特Dtd)"),
    ("迪拜现货", "全球: 现货价: 原油(阿联酋迪拜)"),
    ("穆尔班现货", "全球: 现货均价: 原油(阿联酋穆尔班)"),
)
PRODUCTION_INDICATOR = ("阿联酋原油产量", "阿联酋: 产量: 原油")
RIG_COUNT_INDICATOR = ("阿联酋石油活跃钻机数", "阿联酋石油活跃钻机数")
EIA_PRICE_INDICATORS = (("布伦特现货", "布伦特现货"),)
DUBAI_PRICE_INDICATOR = ("迪拜现货", "全球: 名义商品价格: 迪拜原油")
OPEC_PRODUCTION_INDICATOR = ("阿联酋原油产量", "阿联酋原油产量")
_WORKBOOK_READER = EconomicWorkbookReader(
    "uae_monitoring",
    "monitoring.uae",
)


@dataclass(frozen=True)
class OilMarketData:
    """油价与产量监测所需的最小数据集。"""

    prices: pd.DataFrame
    production: pd.Series
    rig_count: pd.Series | None
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_oil_market_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> OilMarketData:
    """只读取日度油价和月度原油产量，不依赖完整指标字典。"""

    with _WORKBOOK_READER.open_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        if EIA_DAILY_SHEET in excel_file.sheet_names and OPEC_MONTHLY_SHEET in excel_file.sheet_names:
            prices, price_metadata = _WORKBOOK_READER.read_target_sheet(
                excel_file,
                sheet_name=EIA_DAILY_SHEET,
                targets=EIA_PRICE_INDICATORS,
                allowed_frequencies={"日", "日度", "周", "周度"},
                expected_unit="美元/桶",
            )
            dubai_metadata: dict[str, SheetSeriesMetadata] = {}
            if DUBAI_MONTHLY_SHEET in excel_file.sheet_names:
                dubai_prices, dubai_metadata = _WORKBOOK_READER.read_target_sheet(
                    excel_file,
                    sheet_name=DUBAI_MONTHLY_SHEET,
                    targets=(DUBAI_PRICE_INDICATOR,),
                    allowed_frequencies={"月", "月度"},
                    expected_unit="美元/桶",
                )
                prices = prices.join(dubai_prices, how="outer")
            production_frame, production_metadata = _WORKBOOK_READER.read_target_sheet(
                excel_file,
                sheet_name=OPEC_MONTHLY_SHEET,
                targets=(OPEC_PRODUCTION_INDICATOR,),
                allowed_frequencies={"月", "月度"},
                expected_unit="桶/天",
            )
        else:
            dubai_metadata = {}
            prices, price_metadata = _WORKBOOK_READER.read_target_sheet(
                excel_file,
                sheet_name=DAILY_SHEET,
                targets=PRICE_INDICATORS,
                allowed_frequencies={"日", "日度", "周", "周度"},
                expected_unit="美元/桶",
            )
            production_frame, production_metadata = _WORKBOOK_READER.read_target_sheet(
                excel_file,
                sheet_name=MONTHLY_SHEET,
                targets=(PRODUCTION_INDICATOR,),
                allowed_frequencies={"月", "月度"},
                expected_unit="桶/天",
            )
        if RIG_COUNT_SHEET in excel_file.sheet_names:
            rig_count_frame, rig_count_metadata = _WORKBOOK_READER.read_target_sheet(
                excel_file,
                sheet_name=RIG_COUNT_SHEET,
                targets=(RIG_COUNT_INDICATOR,),
                allowed_frequencies={"月", "月度"},
                expected_unit="台",
            )
        else:
            rig_count_frame = None
            rig_count_metadata = {}

    production = production_frame[OPEC_PRODUCTION_INDICATOR[0]].rename(
        OPEC_PRODUCTION_INDICATOR[0]
    )
    rig_count = (
        None
        if rig_count_frame is None
        else rig_count_frame[RIG_COUNT_INDICATOR[0]].rename(
            RIG_COUNT_INDICATOR[0]
        )
    )
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
        source_name=source_name,
    )


__all__ = [
    "OilMarketData",
    "EIA_DAILY_SHEET",
    "OPEC_MONTHLY_SHEET",
    "DUBAI_MONTHLY_SHEET",
    "EIA_PRICE_INDICATORS",
    "DUBAI_PRICE_INDICATOR",
    "OPEC_PRODUCTION_INDICATOR",
    "PRICE_INDICATORS",
    "PRODUCTION_INDICATOR",
    "RIG_COUNT_INDICATOR",
    "RIG_COUNT_SHEET",
    "load_oil_market_data",
]
