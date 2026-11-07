from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from htfa.data.economic_workbook import SheetSeriesMetadata

PMI_SHEET = "月度_LSEG"
PMI_LABEL = "阿联酋非油私营部门采购经理人指数(PMI)"
PMI_INDICATOR = PMI_LABEL
PMI_DISPLAY_NAME = "非油私营部门采购经理指数（PMI）"
DISPLAY_MONTHS = 37


@dataclass(frozen=True)
class PmiData:
    """阿联酋非油私营部门月度 PMI 序列及来源信息。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
