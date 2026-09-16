"""UAE 分析模块共享的月份对齐工具。"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from htfa.data.temporal import (
    latest_complete_month_end_from_values,
)


def latest_complete_month(
    values: pd.DataFrame,
    *,
    today: pd.Timestamp | None = None,
    empty_message: str = "数据没有共同完整月份",
) -> pd.Timestamp:
    """返回所有列都有有效值且已覆盖到月末的最新月份。"""

    complete = values.dropna(how="any").sort_index()
    if complete.empty:
        raise ValueError(empty_message)
    cutoff = latest_complete_month_end_from_values(complete, today=today)
    if cutoff is None:
        raise ValueError(empty_message)
    return pd.Timestamp(cutoff)


def anchor_last_month(
    values: pd.DataFrame,
    *,
    today: pd.Timestamp | None = None,
    empty_message: str = "数据没有共同完整月份",
) -> pd.Period:
    """返回共同有效且已覆盖到月末的最后月份。"""

    latest = latest_complete_month(
        values,
        today=today,
        empty_message=empty_message,
    ).to_period("M")
    return latest


def common_latest_month(
    named_series: Sequence[tuple[str, pd.Series]],
    *,
    today: pd.Timestamp | None = None,
) -> pd.Period:
    """返回所有待展示序列的最后完整自然月中的最早月份。"""

    latest_months: list[pd.Period] = []
    for label, series in named_series:
        clean = series.dropna()
        if clean.empty:
            raise ValueError(f"{label}没有有效观测，无法绘图")
        cutoff = latest_complete_month_end_from_values(clean, today=today)
        if cutoff is None:
            raise ValueError(f"{label}没有完整自然月，无法绘图")
        latest_months.append(pd.Timestamp(cutoff).to_period("M"))
    return min(latest_months)


def through_last_complete_month(
    data: pd.DataFrame | pd.Series,
    *,
    today: pd.Timestamp | None = None,
) -> pd.DataFrame | pd.Series:
    """仅保留截至最后完整自然月的观测；无完整月份时返回空对象。"""

    cutoff = latest_complete_month_end_from_values(data, today=today)
    if cutoff is None:
        return data.iloc[0:0].copy()
    return through_month(data, pd.Timestamp(cutoff).to_period("M"))


def within_month_window(
    data: pd.DataFrame | pd.Series,
    *,
    first_month: pd.Period,
    last_month: pd.Period,
) -> pd.DataFrame | pd.Series:
    """按月份边界截取序列，忽略月份内具体日期差异。"""

    months = pd.DatetimeIndex(data.index).to_period("M")
    return data.loc[(months >= first_month) & (months <= last_month)]


def through_month(
    data: pd.DataFrame | pd.Series,
    last_month: pd.Period,
) -> pd.DataFrame | pd.Series:
    """删除截止月份之后的观测。"""

    months = pd.DatetimeIndex(data.index).to_period("M")
    return data.loc[months <= last_month]


__all__ = [
    "anchor_last_month",
    "common_latest_month",
    "through_last_complete_month",
    "latest_complete_month",
    "through_month",
    "within_month_window",
]
