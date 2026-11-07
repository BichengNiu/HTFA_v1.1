from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.processing.periods import through_last_complete_month
from htfa.monitoring.uae.contracts.oil.war_pressure import (
    PRESSURE_LABEL,
    RAW_LABELS,
    WarPressureData,
)


def _latest_change(
    series: pd.Series, *, days: int | None = None
) -> tuple[float, pd.Timestamp, float | None]:
    clean = series.dropna().sort_index()
    latest_date = pd.Timestamp(clean.index[-1])
    latest_value = float(clean.iloc[-1])
    if days is None:
        base = clean.iloc[-2] if len(clean) >= 2 else None
    else:
        history = clean.loc[: latest_date - pd.Timedelta(days=days)]
        base = history.iloc[-1] if not history.empty else None
    if base is None or float(base) == 0:
        return (latest_value, latest_date, None)
    return (latest_value, latest_date, (latest_value / float(base) - 1) * 100)


def _complete_war_pressure_values(data: WarPressureData) -> pd.DataFrame:
    """删除 WAM 中观测天数不足一个自然月的月度行。"""
    values = data.values.loc[:, [*RAW_LABELS, PRESSURE_LABEL]].sort_index()
    days = data.observation_days.reindex(values.index)
    required_days = pd.PeriodIndex(values.index, freq="M").days_in_month
    complete = days.ge(required_days).fillna(False)
    return values.loc[complete]


def _monthly_mean_series(series: pd.Series) -> pd.Series:
    """将价格序列按自然月取均值，并将索引规范为月末。"""
    clean = through_last_complete_month(series.dropna().sort_index())
    if clean.empty:
        return clean
    periods = pd.DatetimeIndex(clean.index).to_period("M")
    monthly = clean.groupby(periods).mean()
    monthly.index = monthly.index.to_timestamp(how="end").normalize()
    monthly.index.name = "月份"
    return monthly
