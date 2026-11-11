from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.preview.data.economic_workbook import SheetSeriesMetadata

CBUAE_SHEET = "月度_CBUAE"
GOVERNMENT_DEPOSITS = "阿联酋政府存款"
GRE_DEPOSITS = "阿联酋政府控股企业存款"
GOVERNMENT_CREDIT = "阿联酋政府信贷"
GRE_CREDIT = "阿联酋政府控股企业信贷"
CBUAE_INDICATORS: tuple[tuple[str, str], ...] = (
    (GOVERNMENT_DEPOSITS, GOVERNMENT_DEPOSITS),
    (GOVERNMENT_CREDIT, GOVERNMENT_CREDIT),
    (GRE_DEPOSITS, GRE_DEPOSITS),
    (GRE_CREDIT, GRE_CREDIT),
)


@dataclass(frozen=True)
class GovernmentFinanceData:
    """政府及政府控股企业存款与信贷的最小月度数据集。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
