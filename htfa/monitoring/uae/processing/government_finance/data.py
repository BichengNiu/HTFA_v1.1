from __future__ import annotations
from collections.abc import Mapping
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.processing.periods import (
    latest_complete_month as _latest_complete_month,
)
from htfa.monitoring.uae.contracts.government_finance.data import GovernmentFinanceData
from htfa.monitoring.uae.data.government_finance.data import (
    read_government_finance_data,
)


def load_government_finance_data(source: PublishedUAEData) -> GovernmentFinanceData:
    """只读取 ``月度_CBUAE`` 的四个目标指标并校验元数据。"""
    metadata, values = read_government_finance_data(source)
    return GovernmentFinanceData(values=values, metadata=metadata)


def calculate_calendar_yoy(values: pd.DataFrame) -> pd.DataFrame:
    """按完整月历计算同比，缺月时不误用相邻的第 12 条观测。"""
    if values.empty:
        return values.copy()
    monthly = values.copy().sort_index()
    periods = pd.PeriodIndex(pd.DatetimeIndex(monthly.index), freq="M")
    if periods.duplicated().any():
        raise ValueError("月度_CBUAE 包含同月重复观测")
    monthly.index = periods
    complete_index = pd.period_range(periods.min(), periods.max(), freq="M")
    monthly = monthly.reindex(complete_index)
    yoy = monthly.divide(monthly.shift(12)).subtract(1).multiply(100)
    yoy.index = yoy.index.to_timestamp(how="end").normalize()
    return yoy


def display_calendar_yoy(values: pd.DataFrame) -> pd.DataFrame:
    """先用完整历史计算同比，再取最近三年；图表与下载共用同一窗口。"""
    selected = values.dropna(how="all").sort_index()
    if selected.empty:
        return selected
    months = pd.DatetimeIndex(selected.index).to_period("M")
    yoy = calculate_calendar_yoy(selected)
    yoy.index = yoy.index.to_period("M")
    yoy = yoy.reindex(months)
    yoy.index = selected.index
    return yoy.loc[months >= months.max() - 36]


def calendar_yoy_download(
    values: pd.DataFrame, labels: Mapping[str, str]
) -> pd.DataFrame:
    """导出图中的同比、原始存量和上年同期基数，保留派生合计的分项。"""
    display = display_calendar_yoy(values[list(labels)]).rename(columns=labels)
    prior = values.copy()
    prior.index = pd.DatetimeIndex(prior.index).to_period("M") + 12
    prior = prior.reindex(pd.DatetimeIndex(display.index).to_period("M"))
    prior.index = display.index
    return pd.concat(
        [
            display,
            values.reindex(display.index).add_suffix("（原始存量，百万迪拉姆）"),
            prior.add_suffix("（上年同期存量，百万迪拉姆）"),
        ],
        axis=1,
    )


def latest_complete_month(values: pd.DataFrame) -> pd.Timestamp:
    """返回四个指标均有有效值的最新月份。"""
    return _latest_complete_month(
        values, empty_message="月度_CBUAE 没有四个指标均完整的月份"
    )
