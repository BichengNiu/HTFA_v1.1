from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.processing.periods import within_month_window
from htfa.monitoring.uae.contracts.foreign_labor import SERIES_SPECS
from htfa.monitoring.uae.contracts.foreign_labor import DISPLAY_MONTHS
from htfa.monitoring.uae.contracts.foreign_labor import ForeignLaborData
from htfa.monitoring.uae.data.foreign_labor import read_foreign_labor_data


def load_foreign_labor_data(source: PublishedUAEData) -> ForeignLaborData:
    """Read the two official labour-flow series from the foreign-labour sheet."""
    metadata, values = read_foreign_labor_data(source)
    return ForeignLaborData(values=values, metadata=metadata)


def common_observations(values: pd.DataFrame) -> pd.DataFrame:
    """Keep only months with observations for both countries, from their common start."""
    required_columns = [column for column, *_ in SERIES_SPECS]
    missing_columns = [column for column in required_columns if column not in values]
    if missing_columns:
        raise KeyError(f"缺少外籍劳动力图表指标：{missing_columns}")
    shared = values[required_columns].dropna(how="any").sort_index()
    if shared.empty:
        raise ValueError("尼泊尔与孟加拉国没有共同的有效月度观测")
    return shared


def display_foreign_labor_values(values: pd.DataFrame) -> pd.DataFrame:
    """Match the oil charts' trailing three-year display window."""
    shared = common_observations(values)
    last_month = pd.Timestamp(shared.index[-1]).to_period("M")
    return within_month_window(
        shared, first_month=last_month - (DISPLAY_MONTHS - 1), last_month=last_month
    ).rename(columns=dict(SERIES_SPECS))
