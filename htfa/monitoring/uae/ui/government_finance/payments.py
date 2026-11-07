from __future__ import annotations
from collections.abc import Mapping
import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series
from htfa.monitoring.uae.ui.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
)
from htfa.monitoring.uae.processing.sources import source_note
from htfa.monitoring.uae.contracts.government_finance.payments import (
    CUSTOMER_TRANSFERS_NUMBER_DISPLAY,
)
from htfa.monitoring.uae.contracts.government_finance.payments import (
    CUSTOMER_TRANSFER_SERIES,
)
from htfa.monitoring.uae.contracts.government_finance.payments import CHEQUE_SERIES
from htfa.monitoring.uae.contracts.government_finance.payments import PAYMENT_LABELS
from htfa.monitoring.uae.processing.government_finance.payments import (
    payment_display_values,
)


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
        values, series=series, last_month=last_month
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
        ax=create_report_axis(),
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
