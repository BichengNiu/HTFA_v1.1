"""UAE 分析模块共享的月份对齐工具。"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def latest_complete_month(
    values: pd.DataFrame,
    *,
    empty_message: str = "数据没有共同完整月份",
) -> pd.Timestamp:
    """返回所有列都有有效值的最新月份。"""

    complete = values.dropna(how="any").sort_index()
    if complete.empty:
        raise ValueError(empty_message)
    return pd.Timestamp(complete.index[-1])


def anchor_last_month(
    values: pd.DataFrame,
    *,
    today: pd.Timestamp | None = None,
    empty_message: str = "数据没有共同完整月份",
) -> pd.Period:
    """将当前自然月视为未完成，并返回可展示的最后月份。"""

    latest = latest_complete_month(
        values,
        empty_message=empty_message,
    ).to_period("M")
    reference = (
        pd.Timestamp.today()
        if today is None
        else pd.Timestamp(today).normalize()
    ).to_period("M")
    return latest - 1 if latest == reference else latest


def common_latest_month(
    named_series: Sequence[tuple[str, pd.Series]],
) -> pd.Period:
    """返回所有待展示序列都有有效值的最新月份。"""

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
    "latest_complete_month",
    "through_month",
    "within_month_window",
]
