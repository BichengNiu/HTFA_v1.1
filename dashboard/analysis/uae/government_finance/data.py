"""从阿联酋工作簿读取 CBUAE 政府及政府控股企业月度数据。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from dashboard.analysis.uae.oil.data import (
    OilSeriesMetadata,
    _parse_target_sheet,
    _workbook_buffer,
)


CBUAE_SHEET = "月度_CBUAE"
GOVERNMENT_DEPOSITS = "阿联酋政府存款"
GRE_DEPOSITS = "阿联酋政府控股企业存款"
GOVERNMENT_CREDIT = "阿联酋政府信贷"
GRE_CREDIT = "阿联酋政府控股企业信贷"
GOVERNMENT_AND_STATE_CAPITAL_DEPOSITS = "政府及国有资本存款"
GOVERNMENT_AND_STATE_CAPITAL_CREDIT = "政府及国有资本信贷"

CBUAE_INDICATORS: tuple[tuple[str, str], ...] = (
    (GOVERNMENT_DEPOSITS, GOVERNMENT_DEPOSITS),
    (GOVERNMENT_CREDIT, GOVERNMENT_CREDIT),
    (GRE_DEPOSITS, GRE_DEPOSITS),
    (GRE_CREDIT, GRE_CREDIT),
)


@dataclass(frozen=True)
class GovernmentFinanceData:
    """政府及政府控股企业存款与信贷的最小月度数据集。"""

    values: pd.DataFrame
    metadata: dict[str, OilSeriesMetadata]
    source_name: str


def load_government_finance_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> GovernmentFinanceData:
    """只读取 ``月度_CBUAE`` 的四个目标指标并校验元数据。"""

    buffer, source_name = _workbook_buffer(file_input, file_name=file_name)
    excel_file = pd.ExcelFile(buffer)
    try:
        values, metadata = _parse_target_sheet(
            excel_file,
            sheet_name=CBUAE_SHEET,
            targets=CBUAE_INDICATORS,
            allowed_frequencies={"月", "月度"},
            expected_unit="百万迪拉姆",
        )
    finally:
        excel_file.close()

    return GovernmentFinanceData(
        values=values,
        metadata=metadata,
        source_name=source_name,
    )


def calculate_calendar_yoy(values: pd.DataFrame) -> pd.DataFrame:
    """按完整月历计算同比，缺月时不误用相邻的第 12 条观测。"""

    if values.empty:
        return values.copy()
    monthly = values.copy().sort_index()
    periods = pd.PeriodIndex(pd.DatetimeIndex(monthly.index), freq="M")
    if periods.duplicated().any():
        raise ValueError("月度_CBUAE 包含同月重复观测")
    monthly.index = periods
    complete_index = pd.period_range(periods.min(), periods.max(), freq="M")
    monthly = monthly.reindex(complete_index)
    yoy = monthly.divide(monthly.shift(12)).subtract(1).multiply(100)
    yoy.index = yoy.index.to_timestamp(how="end").normalize()
    return yoy


def combine_government_and_state_capital(values: pd.DataFrame) -> pd.DataFrame:
    """Combine government and government-controlled entity bank positions."""

    required_columns = (
        GOVERNMENT_DEPOSITS,
        GRE_DEPOSITS,
        GOVERNMENT_CREDIT,
        GRE_CREDIT,
    )
    missing_columns = [column for column in required_columns if column not in values]
    if missing_columns:
        raise KeyError(f"缺少政府及国有资本合计所需指标：{missing_columns}")

    return pd.DataFrame(
        {
            GOVERNMENT_AND_STATE_CAPITAL_DEPOSITS: values[
                [GOVERNMENT_DEPOSITS, GRE_DEPOSITS]
            ].sum(axis=1, min_count=2),
            GOVERNMENT_AND_STATE_CAPITAL_CREDIT: values[
                [GOVERNMENT_CREDIT, GRE_CREDIT]
            ].sum(axis=1, min_count=2),
        },
        index=values.index,
    )


def latest_complete_month(values: pd.DataFrame) -> pd.Timestamp:
    """返回四个指标均有有效值的最新月份。"""

    complete = values.dropna(how="any").sort_index()
    if complete.empty:
        raise ValueError("月度_CBUAE 没有四个指标均完整的月份")
    return pd.Timestamp(complete.index[-1])


__all__ = [
    "CBUAE_INDICATORS",
    "CBUAE_SHEET",
    "GOVERNMENT_CREDIT",
    "GOVERNMENT_DEPOSITS",
    "GRE_CREDIT",
    "GRE_DEPOSITS",
    "GOVERNMENT_AND_STATE_CAPITAL_CREDIT",
    "GOVERNMENT_AND_STATE_CAPITAL_DEPOSITS",
    "GovernmentFinanceData",
    "calculate_calendar_yoy",
    "combine_government_and_state_capital",
    "latest_complete_month",
    "load_government_finance_data",
]
