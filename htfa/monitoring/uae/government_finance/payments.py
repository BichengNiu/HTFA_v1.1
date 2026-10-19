"""CBUAE customer-transfer and cheque-clearing series used in enterprise activity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.database import (
    PublishedUAEData,
    require_published_source,
)
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.monitoring.uae.periods import within_month_window
from htfa.monitoring.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from htfa.data.economic_workbook import (
    SheetSeriesMetadata,
)


PAYMENT_SHEET = "月度_CBUAE"

CUSTOMER_TRANSFERS_NUMBER = (
    "阿联酋:FTS客户转账笔数(累计)Customer Transfers Number"
)
CUSTOMER_TRANSFERS_AMOUNT = (
    "阿联酋:FTS客户转账金额(累计)Customer Transfers Amount"
)
CHEQUES_NUMBER = "阿联酋:支票清算笔数(累计)Cheques Cleared Number"
CHEQUES_AMOUNT = "阿联酋:支票清算金额(累计)Cheques Cleared Amount"

CUSTOMER_TRANSFERS_NUMBER_DISPLAY = "客户资金转账笔数（FTS）"
CUSTOMER_TRANSFERS_AMOUNT_DISPLAY = "客户资金转账金额（FTS）"
CHEQUES_NUMBER_DISPLAY = "支票清算笔数"
CHEQUES_AMOUNT_DISPLAY = "支票清算金额"

PAYMENT_INDICATORS: tuple[tuple[str, str, str], ...] = (
    (CUSTOMER_TRANSFERS_NUMBER_DISPLAY, CUSTOMER_TRANSFERS_NUMBER, "笔"),
    (CUSTOMER_TRANSFERS_AMOUNT_DISPLAY, CUSTOMER_TRANSFERS_AMOUNT, "百万迪拉姆"),
    (CHEQUES_NUMBER_DISPLAY, CHEQUES_NUMBER, "张"),
    (CHEQUES_AMOUNT_DISPLAY, CHEQUES_AMOUNT, "百万迪拉姆"),
)

CUSTOMER_TRANSFER_SERIES = (
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY,
)
CHEQUE_SERIES = (CHEQUES_NUMBER_DISPLAY, CHEQUES_AMOUNT_DISPLAY)
PAYMENT_LABELS = {
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY: "转账笔数",
    CUSTOMER_TRANSFERS_AMOUNT_DISPLAY: "转账金额",
    CHEQUES_NUMBER_DISPLAY: CHEQUES_NUMBER_DISPLAY,
    CHEQUES_AMOUNT_DISPLAY: CHEQUES_AMOUNT_DISPLAY,
}


@dataclass(frozen=True)
class PaymentData:
    """月度_CBUAE 支付指标及其来源元数据。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]


def load_payment_data(
    source: PublishedUAEData,
) -> PaymentData:
    """读取 FTS 客户转账和支票清算四个累计指标。"""

    source = require_published_source(source)
    with source.open() as tables:
        values, metadata = parse_target_sheet(
            tables, sheet_name=PAYMENT_SHEET,
            targets=tuple((label, indicator) for label, indicator, _ in PAYMENT_INDICATORS),
            allowed_frequencies={"月"},
            expected_unit={label: unit for label, _, unit in PAYMENT_INDICATORS},
        )
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
        consecutive.iloc[1:] = periods[1:] == (periods[:-1] + 1)
    january = pd.Series(periods.month == 1, index=ordered.index)

    monthly = ordered.diff()
    monthly.loc[january] = ordered.loc[january]
    monthly.loc[~consecutive & ~january] = float("nan")
    return monthly


def payment_display_values(
    values: pd.DataFrame, *, series: tuple[str, str], last_month: pd.Period,
) -> pd.DataFrame:
    """统一支付图与下载的当月值，并保留年内累计和连续上月基数。"""
    original = values[list(series)]
    monthly = cumulative_to_monthly(original).rename(columns=PAYMENT_LABELS)
    prior = original.copy()
    prior.index = pd.DatetimeIndex(prior.index).to_period("M") + 1
    prior = prior.reindex(pd.DatetimeIndex(original.index).to_period("M"))
    prior.index = original.index
    frame = pd.concat([
        monthly,
        original.rename(columns=PAYMENT_LABELS).add_suffix("（年内累计）"),
        prior.rename(columns=PAYMENT_LABELS).add_suffix("（上月累计）"),
    ], axis=1)
    return within_month_window(frame, first_month=last_month - 36, last_month=last_month)


def _build_payment_figure(
    values: pd.DataFrame,
    *,
    series: tuple[str, str],
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """用左右双轴绘制一组支付当月值指标。"""

    labels = [PAYMENT_LABELS[name] for name in series]
    display_values = payment_display_values(
        values, series=series, last_month=last_month,
    )[labels].dropna(how="all")
    if display_values.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    axis_units = {
        labels[0]: "笔" if series[0] == CUSTOMER_TRANSFERS_NUMBER_DISPLAY else "张",
        labels[1]: "百万迪拉姆",
    }
    if units is not None:
        axis_units.update({PAYMENT_LABELS[name]: unit for name, unit in units.items()})
    figure, returned_axis = plot_series(
        display_values,
        facet=False,
        axis_groups={labels[0]: "number", labels[1]: "amount"},
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


def build_customer_transfers_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制 FTS 客户转账笔数与金额的当月值双轴图。"""

    return _build_payment_figure(
        values,
        series=CUSTOMER_TRANSFER_SERIES,
        title=title,
        source_text=source_text,
        last_month=last_month,
        units=units,
    )


def build_cheques_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制支票清算笔数与金额的当月值双轴图。"""

    return _build_payment_figure(
        values,
        series=CHEQUE_SERIES,
        title=title,
        source_text=source_text,
        last_month=last_month,
        units=units,
    )


__all__ = [
    "CHEQUES_AMOUNT",
    "CHEQUES_AMOUNT_DISPLAY",
    "CHEQUES_NUMBER",
    "CHEQUES_NUMBER_DISPLAY",
    "CHEQUE_SERIES",
    "CUSTOMER_TRANSFER_SERIES",
    "CUSTOMER_TRANSFERS_AMOUNT",
    "CUSTOMER_TRANSFERS_AMOUNT_DISPLAY",
    "CUSTOMER_TRANSFERS_NUMBER",
    "CUSTOMER_TRANSFERS_NUMBER_DISPLAY",
    "PAYMENT_INDICATORS",
    "PAYMENT_SHEET",
    "PaymentData",
    "build_cheques_figure",
    "build_customer_transfers_figure",
    "cumulative_to_monthly",
    "payment_display_values",
    "load_payment_data",
]
