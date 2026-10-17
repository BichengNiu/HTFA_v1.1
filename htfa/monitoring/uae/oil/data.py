"""阿联酋 V2 油价与原油产量的窄范围工作簿适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from htfa.data.economic_workbook import (
    EconomicWorkbookReader,
    SheetSeriesMetadata,
)
from htfa.data.economic_workbook import SheetSeriesMetadata
from htfa.monitoring.uae.duckdb_reader import read_query


EIA_DAILY_SHEET = "日度_EIA"
OPEC_MONTHLY_SHEET = "月度_OPEC"
DUBAI_MONTHLY_SHEET = "月度_Dubai"
RIG_COUNT_SHEET = "月度_贝克休斯"

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
    rig_count: pd.Series
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_oil_market_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> OilMarketData:
    """读取当前 EIA、Dubai、OPEC 与 Baker Hughes 工作表。"""

    with _WORKBOOK_READER.open_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        prices, price_metadata = _WORKBOOK_READER.read_target_sheet(
            excel_file,
            sheet_name=EIA_DAILY_SHEET,
            targets=EIA_PRICE_INDICATORS,
            allowed_frequencies={"日度"},
            expected_unit="美元/桶",
        )
        dubai_prices, dubai_metadata = _WORKBOOK_READER.read_target_sheet(
            excel_file,
            sheet_name=DUBAI_MONTHLY_SHEET,
            targets=(DUBAI_PRICE_INDICATOR,),
            allowed_frequencies={"月度"},
            expected_unit="美元/桶",
        )
        prices = prices.join(dubai_prices, how="outer")
        production_frame, production_metadata = _WORKBOOK_READER.read_target_sheet(
            excel_file,
            sheet_name=OPEC_MONTHLY_SHEET,
            targets=(OPEC_PRODUCTION_INDICATOR,),
            allowed_frequencies={"月度"},
            expected_unit="桶/天",
        )
        rig_count_frame, rig_count_metadata = _WORKBOOK_READER.read_target_sheet(
            excel_file,
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
        raise ValueError(f"石油监测工作簿缺少有效观测：{empty}")

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


def load_oil_market_from_duckdb() -> OilMarketData:
    """从正式 DuckDB 读取石油页需要的日度和月度序列。"""

    brent = read_query(
        "SELECT period, price_usd_bbl FROM eia_brent_spot_daily ORDER BY period"
    )
    production = read_query(
        "SELECT period, production_bpd FROM opec_crude_production_monthly ORDER BY period"
    )
    dubai = read_query(
        "SELECT period, price_usd_bbl FROM imf_dubai_crude_monthly ORDER BY period"
    )
    rigs = read_query(
        "SELECT period, oil_rigs FROM baker_hughes_monthly ORDER BY period"
    )
    if brent.empty or production.empty:
        raise ValueError("DuckDB 缺少 EIA 布伦特油价或 OPEC 原油产量数据")

    def indexed(frame: pd.DataFrame, column: str, name: str) -> pd.Series:
        return pd.Series(
            frame[column].to_numpy(),
            index=pd.to_datetime(frame["period"]),
            name=name,
        )

    prices = indexed(brent, "price_usd_bbl", "布伦特现货").to_frame()
    if not dubai.empty:
        prices = prices.join(
            indexed(dubai, "price_usd_bbl", DUBAI_PRICE_INDICATOR[0]),
            how="outer",
        )
    oil_production = indexed(
        production,
        "production_bpd",
        OPEC_PRODUCTION_INDICATOR[0],
    )
    rig_count = (
        None if rigs.empty else indexed(rigs, "oil_rigs", RIG_COUNT_INDICATOR[0])
    )
    metadata = {
        "布伦特现货": SheetSeriesMetadata(
            "布伦特现货", "eia_brent_spot_daily.price_usd_bbl", "日度", "美元/桶",
            "EIA", "DuckDB", "eia_brent_spot_daily",
        ),
        OPEC_PRODUCTION_INDICATOR[0]: SheetSeriesMetadata(
            OPEC_PRODUCTION_INDICATOR[0], "opec_crude_production_monthly.production_bpd",
            "月度", "桶/天", "OPEC", "DuckDB", "opec_crude_production_monthly",
        ),
    }
    if DUBAI_PRICE_INDICATOR[0] in prices:
        metadata[DUBAI_PRICE_INDICATOR[0]] = SheetSeriesMetadata(
            DUBAI_PRICE_INDICATOR[0], "imf_dubai_crude_monthly.price_usd_bbl",
            "月度", "美元/桶", "IMF", "DuckDB", "imf_dubai_crude_monthly",
        )
    if rig_count is not None:
        metadata[RIG_COUNT_INDICATOR[0]] = SheetSeriesMetadata(
            RIG_COUNT_INDICATOR[0], "baker_hughes_monthly.oil_rigs",
            "月度", "台", "Baker Hughes", "DuckDB", "baker_hughes_monthly",
        )
    return OilMarketData(
        prices=prices.sort_index(),
        production=oil_production.sort_index(),
        rig_count=None if rig_count is None else rig_count.sort_index(),
        metadata=metadata,
        source_name="uae.duckdb",
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
    "load_oil_market_from_duckdb",
]
