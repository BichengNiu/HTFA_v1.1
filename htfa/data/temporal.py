"""数据源时间覆盖边界工具。

日度/周度源经常在自然月尚未结束时先发布新观测。月度统计若直接使用
最新观测月，会把部分月份误当成完整月份。本模块提供数据管道和分析层
共用的硬性边界：只有覆盖到该自然月最后一天的月份才可作为完整月份。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def last_complete_month_end(
    observed_through: object,
    *,
    today: object | None = None,
) -> date | None:
    """返回观测覆盖到的最后一个完整自然月月末。

    ``observed_through`` 是源数据的最大观测日期。若最大日期早于所在月
    月末，所在月一律视为未完成并回退到上个月；未来日期也不会被使用。
    返回 ``None`` 表示没有可用的完整月份。
    """

    observed = _as_date(observed_through)
    if observed is None:
        return None

    reference = _as_date(today) if today is not None else date.today()
    if reference is None:
        return None
    observed = min(observed, reference)

    year, month = observed.year, observed.month
    month_end = _month_end(year, month)
    if observed < month_end:
        year, month = _previous_month(year, month)
    result = _month_end(year, month)
    if result > reference:
        year, month = _previous_month(year, month)
        result = _month_end(year, month)
    return result


def latest_complete_month_end_from_values(
    values: pd.Series | pd.DataFrame,
    *,
    today: object | None = None,
) -> pd.Timestamp | None:
    """按有效观测日期返回序列的最后完整自然月月末。

    只要求该日期上至少有一个有效值，适用于判断一张日度/周度工作表
    的覆盖边界；多指标共同完整月份由分析层另行使用 ``dropna(how='any')``
    判定。
    """

    import pandas as pd

    clean = (
        values.dropna()
        if isinstance(values, pd.Series)
        else values.dropna(how="all")
    )
    if clean.empty:
        return None
    dates = pd.to_datetime(clean.index, errors="coerce")
    dates = dates[dates.notna()]
    if dates.empty:
        return None
    return last_complete_month_end(dates.max(), today=today)


def _as_date(value: object) -> date | None:
    """把标准库日期/日期时间及常见 ISO 文本转为 date。"""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


def _month_end(year: int, month: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return next_month - timedelta(days=1)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


__all__ = [
    "last_complete_month_end",
    "latest_complete_month_end_from_values",
]
