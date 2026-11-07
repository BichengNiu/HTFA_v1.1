from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
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
