from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
import pandas as pd
from htfa.monitoring.uae.data.database import require_published_source, read_raw_table
from htfa.monitoring.uae.contracts.annual_comparison_contracts import REPORT_UNITS
from htfa.monitoring.uae.contracts.annual import ANNUAL_CHARTS


def load_annual_data(source):
    """Retain observed annual dates and missing values from published sheets."""
    frames = {}
    with open_published_tables(source) as tables:
        for sheet, _, _ in ANNUAL_CHARTS:
            raw = read_raw_table(tables, sheet_name=sheet)
            if set(raw.iloc[2, 1:].dropna()) != {"年"}:
                raise ValueError(f"{sheet} 频率不是年度")
            labels = [str(name).removeprefix(sheet + ":") for name in raw.iloc[1, 1:]]
            for label, unit in zip(labels, raw.iloc[3, 1:], strict=True):
                expected = (
                    REPORT_UNITS[sheet].get(label)
                    if sheet in REPORT_UNITS
                    else "十亿迪拉姆"
                )
                if unit != expected:
                    raise ValueError(f"{sheet} 的 {label} 单位不匹配")
            frame = raw.iloc[6:, 1:].apply(pd.to_numeric, errors="raise")
            frame.index = pd.DatetimeIndex(
                pd.to_datetime(raw.iloc[6:, 0], errors="raise")
            )
            frame.columns = labels
            if frame.index.isna().any() or frame.index.duplicated().any():
                raise ValueError(f"{sheet} 日期异常")
            frame = frame.sort_index().dropna(how="all")
            if frame.empty:
                raise ValueError(f"{sheet} 没有年度观测")
            frames[sheet] = frame
    return frames
