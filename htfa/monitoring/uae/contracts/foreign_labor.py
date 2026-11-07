from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.data.economic_workbook import SheetSeriesMetadata

FOREIGN_LABOR_SHEET = "月度_外籍劳动力"
NEPAL_APPROVALS = "尼泊尔_DoFE批准_含再入境"
BANGLADESH_CLEARANCES = "孟加拉国_BMET出境许可"
NEPAL_LABEL = "尼泊尔劳工人数"
BANGLADESH_LABEL = "孟加拉国劳工人数"
SERIES_SPECS = (
    (NEPAL_APPROVALS, NEPAL_LABEL),
    (BANGLADESH_CLEARANCES, BANGLADESH_LABEL),
)
DISPLAY_MONTHS = 37


@dataclass(frozen=True)
class ForeignLaborData:
    """The two monthly labour-flow series displayed in the companion chart."""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
