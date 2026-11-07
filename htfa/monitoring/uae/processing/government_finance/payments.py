from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.monitoring.uae.processing.periods import within_month_window
from htfa.monitoring.uae.contracts.government_finance.payments import PAYMENT_LABELS
from htfa.monitoring.uae.contracts.government_finance.payments import PaymentData
from htfa.monitoring.uae.data.government_finance.payments import read_payment_data


def load_payment_data(source: PublishedUAEData) -> PaymentData:
    """读取 FTS 客户转账和支票清算四个累计指标。"""
    metadata, values = read_payment_data(source)
    return PaymentData(values=values, metadata=metadata)


def cumulative_to_monthly(values: pd.DataFrame) -> pd.DataFrame:
    """将年内累计支付值转换为当月值。

    每年 1 月保留原始累计值；其他月份仅在存在连续上月观测时做差分。
    如果中间缺月，则该月不臆算，保留为空，直到连续观测恢复。
    """
    ordered = values.sort_index().copy()
    if ordered.empty:
        return ordered
    periods = pd.PeriodIndex(ordered.index, freq="M")
    if periods.duplicated().any():
        raise ValueError("月度支付数据包含同月重复观测")
    consecutive = pd.Series(False, index=ordered.index)
    if len(ordered) > 1:
        consecutive.iloc[1:] = periods[1:] == periods[:-1] + 1
    january = pd.Series(periods.month == 1, index=ordered.index)
    monthly = ordered.diff()
    monthly.loc[january] = ordered.loc[january]
    monthly.loc[~consecutive & ~january] = float("nan")
    return monthly


def payment_display_values(
    values: pd.DataFrame, *, series: tuple[str, str], last_month: pd.Period
) -> pd.DataFrame:
    """统一支付图与下载的当月值，并保留年内累计和连续上月基数。"""
    original = values[list(series)]
    monthly = cumulative_to_monthly(original).rename(columns=PAYMENT_LABELS)
    prior = original.copy()
    prior.index = pd.DatetimeIndex(prior.index).to_period("M") + 1
    prior = prior.reindex(pd.DatetimeIndex(original.index).to_period("M"))
    prior.index = original.index
    frame = pd.concat(
        [
            monthly,
            original.rename(columns=PAYMENT_LABELS).add_suffix("（年内累计）"),
            prior.rename(columns=PAYMENT_LABELS).add_suffix("（上月累计）"),
        ],
        axis=1,
    )
    return within_month_window(
        frame, first_month=last_month - 36, last_month=last_month
    )
