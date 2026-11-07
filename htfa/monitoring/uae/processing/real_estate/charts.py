from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.processing.periods import within_month_window
from htfa.monitoring.uae.contracts.real_estate.charts import COUNT_LABEL
from htfa.monitoring.uae.contracts.real_estate.charts import AMOUNT_LABEL
from htfa.monitoring.uae.contracts.real_estate.charts import AMOUNT_UNIT_FACTOR
from htfa.monitoring.uae.contracts.real_estate.charts import PROPERTY_CONFIG


def sales_display_values(
    values: pd.DataFrame, *, last_month: pd.Period, market: str
) -> pd.DataFrame:
    """返回分市场绘图值及原始百万 AED 金额，图表和下载使用同一口径。"""
    if market not in PROPERTY_CONFIG:
        raise ValueError(f"未知房地产口径：{market}")
    count_column, amount_column = PROPERTY_CONFIG[market]
    display = (
        within_month_window(
            values[[count_column, amount_column]],
            first_month=last_month - 36,
            last_month=last_month,
        )
        .dropna(how="all")
        .rename(columns={count_column: COUNT_LABEL, amount_column: AMOUNT_LABEL})
    )
    display[f"{AMOUNT_LABEL}（百万AED）"] = display[AMOUNT_LABEL]
    display[AMOUNT_LABEL] = display[AMOUNT_LABEL] / AMOUNT_UNIT_FACTOR
    return display
