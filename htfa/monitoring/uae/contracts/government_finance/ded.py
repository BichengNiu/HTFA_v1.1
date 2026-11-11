from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.preview.data.economic_workbook import SheetSeriesMetadata

DED_SHEET = "月度_DED"
ENTERPRISES_INDICATOR = "迪拜:当月有发证活动的企业数(企业号筛重)"
LICENCES_INDICATOR = "迪拜:当月新发执照数(执照号筛重)"
ENTERPRISES_DISPLAY = "有发证活动企业数"
LICENCES_DISPLAY = "当月新发执照数"
DED_INDICATORS: tuple[tuple[str, str], ...] = (
    (ENTERPRISES_DISPLAY, ENTERPRISES_INDICATOR),
    (LICENCES_DISPLAY, LICENCES_INDICATOR),
)
EXPECTED_UNITS = {ENTERPRISES_DISPLAY: "家", LICENCES_DISPLAY: "张"}


@dataclass(frozen=True)
class DedData:
    """迪拜企业发证活动与新发执照的月度序列及来源信息。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
