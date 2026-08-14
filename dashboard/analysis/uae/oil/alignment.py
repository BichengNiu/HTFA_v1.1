"""石油面板多指标时间范围对齐。"""

from __future__ import annotations

import pandas as pd


def common_latest_month(
    named_series: list[tuple[str, pd.Series]],
) -> pd.Period:
    """返回所有待展示指标均有数据的最新月份。"""

    latest_months: list[pd.Period] = []
    for label, series in named_series:
        clean = series.dropna()
        if clean.empty:
            raise ValueError(f"{label}没有有效观测，无法绘图")
        latest_months.append(pd.Timestamp(clean.index.max()).to_period("M"))
    return min(latest_months)


def within_month_window(
    data: pd.DataFrame | pd.Series,
    *,
    first_month: pd.Period,
    last_month: pd.Period,
) -> pd.DataFrame | pd.Series:
    """按月份边界截取时间序列，不受月内具体日期差异影响。"""

    months = pd.DatetimeIndex(data.index).to_period("M")
    return data.loc[(months >= first_month) & (months <= last_month)]


def through_month(
    data: pd.DataFrame | pd.Series,
    last_month: pd.Period,
) -> pd.DataFrame | pd.Series:
    """删除共同截止月份之后的观测。"""

    months = pd.DatetimeIndex(data.index).to_period("M")
    return data.loc[months <= last_month]


__all__ = ["common_latest_month", "through_month", "within_month_window"]
