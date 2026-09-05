"""普通表格中的时间列推断。"""

from __future__ import annotations

import pandas as pd


def infer_time_values(values: pd.Series) -> pd.Series | None:
    """将一列完整推断为日期；无法完整推断时返回 None。"""
    if pd.api.types.is_datetime64_any_dtype(values):
        return values
    if pd.api.types.is_numeric_dtype(values):
        return None

    nonblank = values.notna() & values.astype(str).str.strip().ne("")
    if not nonblank.any():
        return None
    parsed = pd.to_datetime(values, errors="coerce", format="mixed")
    if not parsed.loc[nonblank].notna().all():
        return None
    return parsed


__all__ = ["infer_time_values"]
