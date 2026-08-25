"""CBUAE customer-transfer and cheque-clearing series used in enterprise activity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.periods import within_month_window
from dashboard.analysis.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    format_updated_at,
    open_uae_workbook,
    optional_text,
    validate_sheet,
)
from dashboard.preview.core.workbook_parser import normalize_indicator_name


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


@dataclass(frozen=True)
class PaymentData:
    """月度_CBUAE 支付指标及其来源元数据。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_payment_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> PaymentData:
    """读取 FTS 客户转账和支票清算四个累计指标。"""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        values, metadata = _parse_payment_sheet(excel_file)
    return PaymentData(values=values, metadata=metadata, source_name=source_name)


def _parse_payment_sheet(
    excel_file: pd.ExcelFile,
) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
    """严格解析月度_CBUAE 中四个不同单位的支付指标。"""

    if PAYMENT_SHEET not in excel_file.sheet_names:
        raise ValueError(f"工作簿缺少“{PAYMENT_SHEET}”sheet")

    raw = pd.read_excel(excel_file, sheet_name=PAYMENT_SHEET, header=None)
    validate_sheet(raw, PAYMENT_SHEET)

    normalized_targets = {
        normalize_indicator_name(indicator_name): (display_name, unit)
        for display_name, indicator_name, unit in PAYMENT_INDICATORS
    }
    candidate_columns: dict[str, list[int]] = {}
    for column_index in range(1, raw.shape[1]):
        indicator_name = normalize_indicator_name(raw.iloc[1, column_index])
        if indicator_name in normalized_targets:
            display_name, _ = normalized_targets[indicator_name]
            candidate_columns.setdefault(display_name, []).append(column_index)

    matching_columns: dict[str, int] = {}
    for display_name, indicator_name, unit in PAYMENT_INDICATORS:
        columns = candidate_columns.get(display_name, [])
        compatible = [
            column_index
            for column_index in columns
            if optional_text(raw.iloc[2, column_index]) in {"月", "月度"}
            and optional_text(raw.iloc[3, column_index]) == unit
            and bool(optional_text(raw.iloc[4, column_index]))
        ]
        if len(compatible) != 1:
            if not columns:
                raise ValueError(f"sheet“{PAYMENT_SHEET}”缺少指标：{indicator_name}")
            raise ValueError(
                f"指标“{indicator_name}”应有唯一一列月度、{unit}、且来源非空的观测"
            )
        matching_columns[display_name] = compatible[0]

    data_block = raw.iloc[6:, :].dropna(how="all")
    dates = pd.to_datetime(data_block.iloc[:, 0], errors="coerce")
    if dates.isna().any():
        row_number = int(dates[dates.isna()].index[0]) + 1
        raise ValueError(f"sheet“{PAYMENT_SHEET}”第{row_number}行日期无效")
    if dates.duplicated().any():
        raise ValueError(f"sheet“{PAYMENT_SHEET}”包含重复日期")

    series_map: dict[str, pd.Series] = {}
    metadata: dict[str, SheetSeriesMetadata] = {}
    for display_name, indicator_name, _ in PAYMENT_INDICATORS:
        column_index = matching_columns[display_name]
        raw_values = data_block.iloc[:, column_index]
        numeric = pd.to_numeric(raw_values, errors="coerce")
        invalid = (
            raw_values.notna()
            & raw_values.astype(str).str.strip().ne("")
            & numeric.isna()
        )
        if invalid.any():
            row_number = int(invalid[invalid].index[0]) + 1
            raise ValueError(
                f"sheet“{PAYMENT_SHEET}”指标“{indicator_name}”"
                f"第{row_number}行不是数值"
            )
        series = pd.Series(
            numeric.mask(numeric.eq(0)).to_numpy(),
            index=pd.DatetimeIndex(dates),
            name=display_name,
        ).dropna().sort_index()
        if series.empty:
            raise ValueError(f"指标“{indicator_name}”没有非零有效观测")
        series_map[display_name] = series
        metadata[display_name] = SheetSeriesMetadata(
            display_name=display_name,
            indicator_name=normalize_indicator_name(
                raw.iloc[1, column_index]
            ),
            frequency=optional_text(raw.iloc[2, column_index]),
            unit=optional_text(raw.iloc[3, column_index]),
            source=optional_text(raw.iloc[4, column_index]),
            updated_at=format_updated_at(raw.iloc[5, column_index]),
            sheet_name=PAYMENT_SHEET,
        )

    return (
        pd.concat(
            [series_map[display_name] for display_name, *_ in PAYMENT_INDICATORS],
            axis=1,
            sort=False,
        ).sort_index(),
        metadata,
    )


def cumulative_to_monthly(values: pd.DataFrame) -> pd.DataFrame:
    """将年内累计支付值转换为当月值。

    每年 1 月保留原始累计值；其他月份仅在存在连续上月观测时做差分。
    如果中间缺月，则该月不臆算，保留为空，直到连续观测恢复。
    """

    ordered = values.sort_index().copy()
    if ordered.empty:
        return ordered

    periods = pd.PeriodIndex(ordered.index, freq="M")
    consecutive = pd.Series(False, index=ordered.index)
    if len(ordered) > 1:
        consecutive.iloc[1:] = periods[1:] == (periods[:-1] + 1)
    january = pd.Series(periods.month == 1, index=ordered.index)

    monthly = ordered.diff()
    monthly.loc[january] = ordered.loc[january]
    monthly.loc[~consecutive & ~january] = float("nan")
    return monthly


def _build_payment_figure(
    values: pd.DataFrame,
    *,
    series: tuple[str, str],
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
    legend_labels: tuple[str, str] | None = None,
) -> Figure:
    """用左右双轴绘制一组支付当月值指标。"""

    monthly_values = cumulative_to_monthly(values[list(series)])
    display_values = within_month_window(
        monthly_values,
        first_month=last_month - 36,
        last_month=last_month,
    ).dropna(how="all")
    if display_values.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    axis_units = {
        series[0]: "笔" if series[0] == CUSTOMER_TRANSFERS_NUMBER_DISPLAY else "张",
        series[1]: "百万迪拉姆",
    }
    if units is not None:
        axis_units.update(units)
    figure, returned_axis = plot_series(
        display_values,
        facet=False,
        axis_groups={series[0]: "number", series[1]: "amount"},
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        legend_labels=legend_labels,
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
        legend_labels=("转账笔数（左轴）", "转账金额（右轴）"),
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
    "load_payment_data",
]
