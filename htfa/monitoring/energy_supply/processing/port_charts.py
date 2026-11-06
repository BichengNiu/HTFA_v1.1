"""Port call aggregation and charts using the pinned Ts public API."""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, timedelta

from htfa.monitoring.energy_supply.contracts.records import SHIP_TYPE_LABELS

AGGREGATIONS = {"日度": "每日", "周度": "每周", "月度": "每月", "年度": "年度"}
TIME_RANGES = ["近1周", "近1个月", "近1个季度", "近半年", "近1年", "近3年", "近5年", "近10年", "全部"]




def window_start(last: date, period: str, earliest: date) -> date:
    """Inclusive rolling calendar window, bounded by the local history."""
    if period == "全部":
        return earliest
    if period == "近1周":
        return max(earliest, last-timedelta(days=6))
    months = {"近1个月": 1, "近1个季度": 3, "近半年": 6,
              "近1年": 12, "近3年": 36, "近5年": 60, "近10年": 120}[period]
    year, month = divmod(last.year*12+last.month-1-months, 12)
    month += 1
    start = date(year, month, min(last.day, calendar.monthrange(year, month)[1]))+timedelta(days=1)
    return max(earliest, start)


def series_labels(aggregation="日度") -> dict[str, str]:
    prefix = AGGREGATIONS[aggregation]
    return {"portcalls": f"{prefix}进港艘次", **{
        f"portcalls_{kind}": f"{label}{prefix}进港艘次" for kind, label in SHIP_TYPE_LABELS.items()
    }}


def aggregate_rows(rows: tuple, first_day: date, aggregation="日度") -> list[dict]:
    """Sum the selected date window; missing days/values remain unknown."""
    if aggregation not in AGGREGATIONS:
        raise ValueError("未知聚合方式")
    selected = sorted((row for row in rows if row[0] >= first_day), key=lambda row: row[0])
    if not selected:
        return []
    if len({row[0] for row in selected}) != len(selected):
        raise ValueError("每日进港统计存在重复日期")
    first, last = selected[0][0], selected[-1][0]
    fields = tuple(series_labels(aggregation))
    groups = defaultdict(list)
    for row in selected:
        day = row[0]
        start = (day - timedelta(days=day.weekday()) if aggregation == "周度" else
                 day.replace(day=1) if aggregation == "月度" else
                 day.replace(month=1, day=1) if aggregation == "年度" else day)
        groups[start].append(row)
    result = []
    for start, group in groups.items():
        end = (start+timedelta(days=6) if aggregation == "周度" else
               start.replace(day=calendar.monthrange(start.year, start.month)[1]) if aggregation == "月度" else
               start.replace(month=12, day=31) if aggregation == "年度" else start)
        actual_start, actual_end = max(start, first), min(end, last)
        complete = len(group) == (actual_end-actual_start).days+1
        record = {"date": start, "period_start": actual_start, "period_end": actual_end}
        for index, field in enumerate(fields, 1):
            values = [row[index] for row in group]
            record[field] = (sum(values) if complete and all(
                value is not None and math.isfinite(value) and value >= 0 for value in values
            ) else None)
        result.append(record)
    return result
