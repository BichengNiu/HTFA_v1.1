"""月度_CBUAE 的私人企业/个人信贷与外资流入指标（loader + 图表）。

外资流入取最能体现境外资金进入银行系统的存量指标：银行外债、外币存款，与非居民
存款合计「外国主体存款」（= 非居民私人企业 + 个人 + 政府及非商业实体三个互斥分项；
月度存量，表征外资流入须结合环比增量解读，不含 FDI）。

企业 + 居民信贷取私人企业信贷（Corporate）、个人信贷（Individual）与工商业贷款
（商业及工业部门信贷 Business & Industrial），按整月历同比（%），与「政府及国有
资本」图同口径。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.database import PublishedUAEData, require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.monitoring.uae.government_finance.data import display_calendar_yoy
from htfa.monitoring.uae.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from htfa.data.economic_workbook import SheetSeriesMetadata


CBUAE_SHEET = "月度_CBUAE"

FOREIGN_LIABILITIES = "阿联酋:银行国外负债(Foreign Liabilities)"
FOREIGN_LIABILITIES_DISPLAY = "银行外债"
FOREIGN_CURRENCIES = "阿联酋:外币存款(Total Foreign Currencies)"
FOREIGN_CURRENCIES_DISPLAY = "外币存款"
NONRESIDENT_DEPOSITS = "外国主体存款"
# 外国主体存款 = 非居民私人企业存款 + 非居民个人存款 + 非居民政府及非商业实体存款
# （非居民块(2) 的三个互斥分项；商业及工业部门存款/其他金融企业存款均为私人企业的子项，不能重复计入）
NONRESIDENT_CORPORATE = "阿联酋:非居民存款:私人企业存款(Private Corporate Deposit)"
NONRESIDENT_CORPORATE_DISPLAY = "非居民私人企业存款"
NONRESIDENT_INDIVIDUALS = "阿联酋:非居民存款:个人存款(Individuals Deposit)"
NONRESIDENT_INDIVIDUALS_DISPLAY = "非居民个人存款"
NONRESIDENT_GOVERNMENT = "阿联酋:非居民存款:政府及非商业实体存款(Government & Non Commercial Entities Deposit)"
NONRESIDENT_GOVERNMENT_DISPLAY = "非居民政府及非商业实体存款"
PRIVATE_CORPORATE = "阿联酋:国内信贷:私人企业信贷(Private Corporate Credit)"
PRIVATE_CORPORATE_DISPLAY = "私人企业信贷"
INDIVIDUAL = "阿联酋:国内信贷:个人信贷(Individual Credit)"
INDIVIDUAL_DISPLAY = "个人信贷"
BUSINESS_INDUSTRIAL = "阿联酋:国内信贷:商业及工业部门信贷(Business & Industrial Sector Credit)"
BUSINESS_INDUSTRIAL_DISPLAY = "工商业贷款"

FOREIGN_INFLOW_INDICATORS: tuple[tuple[str, str], ...] = (
    (FOREIGN_LIABILITIES_DISPLAY, FOREIGN_LIABILITIES),
    (FOREIGN_CURRENCIES_DISPLAY, FOREIGN_CURRENCIES),
    (NONRESIDENT_CORPORATE_DISPLAY, NONRESIDENT_CORPORATE),
    (NONRESIDENT_INDIVIDUALS_DISPLAY, NONRESIDENT_INDIVIDUALS),
    (NONRESIDENT_GOVERNMENT_DISPLAY, NONRESIDENT_GOVERNMENT),
)
PRIVATE_CREDIT_INDICATORS: tuple[tuple[str, str], ...] = (
    (PRIVATE_CORPORATE_DISPLAY, PRIVATE_CORPORATE),
    (INDIVIDUAL_DISPLAY, INDIVIDUAL),
    (BUSINESS_INDUSTRIAL_DISPLAY, BUSINESS_INDUSTRIAL),
)


FOREIGN_SERIES = (
    f"{FOREIGN_LIABILITIES_DISPLAY}同比",
    f"{FOREIGN_CURRENCIES_DISPLAY}同比",
    f"{NONRESIDENT_DEPOSITS}同比",
)
PRIVATE_CREDIT_SERIES = (
    f"{PRIVATE_CORPORATE_DISPLAY}同比",
    f"{INDIVIDUAL_DISPLAY}同比",
    f"{BUSINESS_INDUSTRIAL_DISPLAY}同比",
)


@dataclass(frozen=True)
class CbuaeSeriesData:
    """月度_CBUAE 的一组扩展指标（外资流入或企业/居民信贷）。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]


def load_foreign_inflow_data(
    source: PublishedUAEData,
) -> CbuaeSeriesData:
    """读取外资流入三个指标：银行外债、外币存款与外国主体存款（非居民存款合计）。"""

    data = _load_cbuae_series(source, targets=FOREIGN_INFLOW_INDICATORS)
    frame = data.values
    nonresident = frame[
        [
            NONRESIDENT_CORPORATE_DISPLAY,
            NONRESIDENT_INDIVIDUALS_DISPLAY,
            NONRESIDENT_GOVERNMENT_DISPLAY,
        ]
    ].sum(axis=1, min_count=3)
    frame = frame.copy()
    frame[NONRESIDENT_DEPOSITS] = nonresident
    return CbuaeSeriesData(
        values=frame,
        metadata=data.metadata,
    )


def load_private_credit_data(
    source: PublishedUAEData,
) -> CbuaeSeriesData:
    """读取私人企业、个人和工商业贷款三个指标。"""

    return _load_cbuae_series(
        source,
        targets=PRIVATE_CREDIT_INDICATORS,
    )


def _load_cbuae_series(
    source: PublishedUAEData,
    *,
    targets: tuple[tuple[str, str], ...],
) -> CbuaeSeriesData:
    source = require_published_source(source)
    with source.open() as tables:
        frame, metadata = parse_target_sheet(
            tables,
            sheet_name=CBUAE_SHEET,
            targets=targets,
            allowed_frequencies={"月", "月度"},
            expected_unit="百万迪拉姆",
        )
    return CbuaeSeriesData(
        values=frame,
        metadata=metadata,
    )


def _common_line_setup(
    frame: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None,
) -> Figure:
    figure, returned_axis = plot_series(
        frame,
        facet=False,
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
        units=units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


def build_foreign_inflow_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制银行外债、外币存款与外国主体存款同比，先算同比再取最近三年。"""

    inflow_columns = [
        FOREIGN_LIABILITIES_DISPLAY,
        FOREIGN_CURRENCIES_DISPLAY,
        NONRESIDENT_DEPOSITS,
    ]
    frame = display_calendar_yoy(values[inflow_columns]).add_suffix("同比")
    if frame.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    axis_units = {name: "%" for name in FOREIGN_SERIES}
    if units is not None:
        axis_units.update(units)
    return _common_line_setup(
        frame,
        title=title,
        source_text=source_text,
        units=axis_units,
    )


def build_private_credit_yoy_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制私人企业、个人及工商业贷款同比，先算同比再取最近三年。"""

    credit_columns = [
        PRIVATE_CORPORATE_DISPLAY,
        INDIVIDUAL_DISPLAY,
        BUSINESS_INDUSTRIAL_DISPLAY,
    ]
    frame = display_calendar_yoy(values[credit_columns]).add_suffix("同比")
    if frame.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    axis_units = {name: "%" for name in PRIVATE_CREDIT_SERIES}
    if units is not None:
        axis_units.update(units)
    return _common_line_setup(
        frame,
        title=title,
        source_text=source_text,
        units=axis_units,
    )


__all__ = [
    "BUSINESS_INDUSTRIAL",
    "BUSINESS_INDUSTRIAL_DISPLAY",
    "CBUAE_SHEET",
    "CbuaeSeriesData",
    "FOREIGN_CURRENCIES",
    "FOREIGN_CURRENCIES_DISPLAY",
    "FOREIGN_INFLOW_INDICATORS",
    "FOREIGN_LIABILITIES",
    "FOREIGN_LIABILITIES_DISPLAY",
    "FOREIGN_SERIES",
    "INDIVIDUAL",
    "INDIVIDUAL_DISPLAY",
    "NONRESIDENT_CORPORATE",
    "NONRESIDENT_CORPORATE_DISPLAY",
    "NONRESIDENT_DEPOSITS",
    "NONRESIDENT_GOVERNMENT",
    "NONRESIDENT_GOVERNMENT_DISPLAY",
    "NONRESIDENT_INDIVIDUALS",
    "NONRESIDENT_INDIVIDUALS_DISPLAY",
    "PRIVATE_CORPORATE",
    "PRIVATE_CORPORATE_DISPLAY",
    "PRIVATE_CREDIT_INDICATORS",
    "PRIVATE_CREDIT_SERIES",
    "build_foreign_inflow_figure",
    "build_private_credit_yoy_figure",
    "load_foreign_inflow_data",
    "load_private_credit_data",
]
