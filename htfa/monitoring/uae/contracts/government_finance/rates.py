from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.preview.data.economic_workbook import SheetSeriesMetadata

RATES_SHEET = "日度_Wind"
EIBOR_OVERNIGHT_DISPLAY = "阿联酋银行间市场拆借利率（隔夜）"
EIBOR_ONEYEAR_DISPLAY = "阿联酋银行间市场拆借利率（1年期）"
US_OVERNIGHT_DISPLAY = "美国银行间市场拆借利率（隔夜）"
EIBOR_OVERNIGHT_INDICATOR = "阿联酋:银行间同业拆借利率(EIBOR):隔夜"
EIBOR_ONEYEAR_INDICATOR = "阿联酋:银行间同业拆借利率(EIBOR):1年"
US_OVERNIGHT_INDICATOR = "美国:有效联邦基金利率(EFFR)"
RATES_INDICATORS: tuple[tuple[str, str], ...] = (
    (EIBOR_OVERNIGHT_DISPLAY, EIBOR_OVERNIGHT_INDICATOR),
    (EIBOR_ONEYEAR_DISPLAY, EIBOR_ONEYEAR_INDICATOR),
    (US_OVERNIGHT_DISPLAY, US_OVERNIGHT_INDICATOR),
)
RATES_SERIES = (EIBOR_OVERNIGHT_DISPLAY, EIBOR_ONEYEAR_DISPLAY, US_OVERNIGHT_DISPLAY)
ALLOWED_FREQUENCIES = {"日", "日度", "月", "月度"}


@dataclass(frozen=True)
class RatesData:
    """EIBOR 隔夜/1年与美国 EFFR 的月度均值数据与元数据。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
