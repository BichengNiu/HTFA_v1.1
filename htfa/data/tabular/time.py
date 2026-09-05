"""普通表格中的时间列推断。"""

from __future__ import annotations

import pandas as pd


def parse_time_values(
    values: pd.Series,
    *,
    reject_numeric: bool,
    require_nonblank: bool,
) -> pd.Series | None:
    """按指定策略解析一列时间值。

    Parameters
    ----------
    values:
        待解析的 pandas Series。
    reject_numeric:
        是否把数值列视为非时间列。
    require_nonblank:
        是否要求至少存在一个非空值。
    """
    if pd.api.types.is_datetime64_any_dtype(values):
        return values
    if reject_numeric and pd.api.types.is_numeric_dtype(values):
        return None

    nonblank = values.notna() & values.astype(str).str.strip().ne("")
    if require_nonblank and not nonblank.any():
        return None
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    if not parsed.loc[nonblank].notna().all():
        return None
    return parsed


def infer_time_values(values: pd.Series) -> pd.Series | None:
    """将一列完整推断为日期；无法完整推断时返回 None。"""
    return parse_time_values(
        values,
        reject_numeric=True,
        require_nonblank=True,
    )


__all__ = ["infer_time_values"]
