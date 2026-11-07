from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.data.database import read_report_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.data.temporal import last_complete_month_end

_HIGH_FREQUENCY_LABELS = frozenset(
    {"日", "日度", "周", "周度", "旬", "旬度", "月", "月度"}
)


def _latest_high_frequency_month(
    source: PublishedUAEData, *, today: pd.Timestamp | None = None
) -> pd.Period:
    observation_cutoff = (
        pd.Timestamp.today().normalize()
        if today is None
        else pd.Timestamp(today).normalize()
    )
    latest_months: list[pd.Period] = []
    for sheet_name, raw in read_report_tables(source).items():
        frequencies = {
            str(value).strip() for value in raw.iloc[2, 1:].tolist() if pd.notna(value)
        }
        if not frequencies & _HIGH_FREQUENCY_LABELS:
            continue
        dates = pd.to_datetime(raw.iloc[6:, 0], errors="coerce")
        values = raw.iloc[6:, 1:].apply(pd.to_numeric, errors="coerce")
        valid = (
            dates.notna() & dates.le(observation_cutoff) & values.notna().any(axis=1)
        )
        if not valid.any():
            raise ValueError(f"高频工作表“{sheet_name}”没有可用日期或数值观测")
        candidate = pd.Timestamp(dates[valid].max())
        candidate_month = candidate.to_period("M")
        if frequencies & {"日", "日度", "周", "周度", "旬", "旬度"}:
            cutoff = last_complete_month_end(
                candidate.date(), today=observation_cutoff.date()
            )
            if cutoff is None:
                continue
            latest_months.append(pd.Timestamp(cutoff).to_period("M"))
        else:
            if candidate_month == observation_cutoff.to_period("M"):
                candidate_month -= 1
            latest_months.append(candidate_month)
    if not latest_months:
        raise ValueError("数据库报告没有可用于报告标题的完整高频月份")
    return max(latest_months)
