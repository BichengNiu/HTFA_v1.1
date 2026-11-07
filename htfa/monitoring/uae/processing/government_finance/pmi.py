from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.processing.periods import within_month_window
from htfa.monitoring.uae.contracts.government_finance.pmi import DISPLAY_MONTHS
from htfa.monitoring.uae.contracts.government_finance.pmi import PmiData
from htfa.monitoring.uae.data.government_finance.pmi import read_pmi_data


def load_pmi_data(source: PublishedUAEData) -> PmiData:
    """只读取 ``月度_LSEG`` 的单一 PMI 指标并校验元数据。"""
    metadata, values = read_pmi_data(source)
    return PmiData(values=values, metadata=metadata)


def display_pmi_values(values: pd.DataFrame) -> pd.DataFrame:
    """返回最近展示窗口内的 PMI 序列。"""
    last_month = pd.Timestamp(values.index[-1]).to_period("M")
    return within_month_window(
        values, first_month=last_month - (DISPLAY_MONTHS - 1), last_month=last_month
    )
