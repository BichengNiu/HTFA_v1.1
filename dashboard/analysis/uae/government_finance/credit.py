"""月度_CBUAE 的私人企业/个人信贷与外资流入指标（loader + 图表）。

外资流入取最能体现境外资金进入银行系统的存量指标：银行外债、外币存款，与非居民
存款合计「外国主体存款」（= 非居民私人企业 + 个人 + 政府及非商业实体三个互斥分项；
月度存量，表征外资流入须结合环比增量解读，不含 FDI）。

企业 + 居民信贷取私人企业信贷（Corporate）、个人信贷（Individual）与工商业贷款
（商业及工业部门信贷 Business & Industrial），按整月历同比（%），与「政府及国有
资本」图同口径。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.government_finance.data import calculate_calendar_yoy
from dashboard.analysis.uae.plot_helpers import (
    WAR_LINE_COLOR,
    WAR_START_DATE,
    add_bottom_legend,
    add_source_note,
    annotate_war,
    finish_dual_axis_figure,
    matching_line_handles,
    normalize_ts_axis,
)
from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    open_uae_workbook,
    parse_target_sheet,
)


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
    (f"{FOREIGN_LIABILITIES_DISPLAY}同比", "#000000"),
    (f"{FOREIGN_CURRENCIES_DISPLAY}同比", "#1F4E79"),
    (f"{NONRESIDENT_DEPOSITS}同比", "#6B7280"),
)
PRIVATE_CREDIT_SERIES = (
    (f"{PRIVATE_CORPORATE_DISPLAY}同比", "#000000"),
    (f"{INDIVIDUAL_DISPLAY}同比", "#1F4E79"),
    (f"{BUSINESS_INDUSTRIAL_DISPLAY}同比", "#6B7280"),
)


@dataclass(frozen=True)
class CbuaeSeriesData:
    """月度_CBUAE 的一组扩展指标（外资流入或企业/居民信贷）。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_foreign_inflow_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> CbuaeSeriesData:
    """读取外资流入三个指标：银行外债、外币存款与外国主体存款（非居民存款合计）。"""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        frame, metadata = parse_target_sheet(
            excel_file,
            sheet_name=CBUAE_SHEET,
            targets=FOREIGN_INFLOW_INDICATORS,
            allowed_frequencies={"月", "月度"},
            expected_unit="百万迪拉姆",
        )
    nonresident = frame[
        [
            NONRESIDENT_CORPORATE_DISPLAY,
            NONRESIDENT_INDIVIDUALS_DISPLAY,
            NONRESIDENT_GOVERNMENT_DISPLAY,
        ]
    ].sum(axis=1, min_count=3)
    frame = frame[
        [FOREIGN_LIABILITIES_DISPLAY, FOREIGN_CURRENCIES_DISPLAY]
    ].copy()
    frame[NONRESIDENT_DEPOSITS] = nonresident
    frame = frame.sort_index()
    if frame.empty:
        raise ValueError(f"{CBUAE_SHEET} 没有可用的外资流入指标观测")
    return CbuaeSeriesData(
        values=frame,
        metadata=metadata,
        source_name=source_name,
    )


def load_private_credit_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> CbuaeSeriesData:
    """读取企业及居民信贷两个指标（私人企业信贷、个人信贷）。"""

    return _load_cbuae_series(
        file_input,
        targets=PRIVATE_CREDIT_INDICATORS,
        file_name=file_name,
    )


def _load_cbuae_series(
    file_input: Any,
    *,
    targets: tuple[tuple[str, str], ...],
    file_name: str | None,
) -> CbuaeSeriesData:
    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        frame, metadata = parse_target_sheet(
            excel_file,
            sheet_name=CBUAE_SHEET,
            targets=targets,
            allowed_frequencies={"月", "月度"},
            expected_unit="百万迪拉姆",
        )
    frame = frame.sort_index()
    if frame.empty:
        raise ValueError(f"{CBUAE_SHEET} 没有可用的扩展指标观测")
    return CbuaeSeriesData(
        values=frame,
        metadata=metadata,
        source_name=source_name,
    )


def _common_line_setup(
    frame: pd.DataFrame,
    series_specs: tuple[tuple[str, str], ...],
    *,
    title: str,
    source_text: str,
    ytitle: str,
) -> tuple[Figure, object]:
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=title,
        xtitle="",
        ytitle=ytitle,
        ytitle_position="side",
        colors=[color for _, color in series_specs],
        linewidth=2.2,
        markersize=0,
        max_ticks=8,
        year_ruler=True,
        vlines=WAR_START_DATE,
        vline_color=WAR_LINE_COLOR,
        vline_linestyle="--",
        vline_linewidth=1.5,
        show_legend=False,
        note=None,
        grid=True,
        title_loc="center",
        title_pad=14,
    )
    axis = normalize_ts_axis(returned_axis)
    axis.title.set_fontweight("normal")
    axis.set_ylabel(ytitle, fontsize=12)
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color("#6B7280")
        spine.set_linewidth(0.9)
    annotate_war(axis)
    add_bottom_legend(
        figure,
        matching_line_handles(
            axis,
            [display_name for display_name, _ in series_specs],
        ),
        [display_name for display_name, _ in series_specs],
        ncol=len(series_specs),
    )
    finish_dual_axis_figure(figure, top=0.90)
    add_source_note(figure, source_text)
    return figure, axis


def build_foreign_inflow_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """绘制银行外债、外币存款与外国主体存款的同比三线图（%），先算同比再取最近 36 个月。"""

    selected = values.dropna(how="all").sort_index()
    if selected.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    inflow_columns = [
        FOREIGN_LIABILITIES_DISPLAY,
        FOREIGN_CURRENCIES_DISPLAY,
        NONRESIDENT_DEPOSITS,
    ]
    yoy = calculate_calendar_yoy(selected[inflow_columns]).reindex(
        selected.index
    )
    periods = pd.PeriodIndex(pd.DatetimeIndex(yoy.index), freq="M")
    last_month = periods.max()
    display_yoy = yoy.loc[periods >= last_month - 36]
    frame = pd.DataFrame(
        {f"{column}同比": display_yoy[column] for column in inflow_columns}
    )
    figure, axis = _common_line_setup(
        frame,
        FOREIGN_SERIES,
        title=title,
        source_text=source_text,
        ytitle="同比（%）",
    )
    axis.axhline(0, color="#6B7280", linewidth=0.8, zorder=0)
    return figure


def build_private_credit_yoy_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """绘制私人企业信贷与个人信贷的同比双线图（%），先算同比再取最近 36 个月。"""

    selected = values.dropna(how="all").sort_index()
    if selected.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    credit_columns = [
        PRIVATE_CORPORATE_DISPLAY,
        INDIVIDUAL_DISPLAY,
        BUSINESS_INDUSTRIAL_DISPLAY,
    ]
    yoy = calculate_calendar_yoy(
        selected[credit_columns]
    ).reindex(selected.index)
    periods = pd.PeriodIndex(pd.DatetimeIndex(yoy.index), freq="M")
    last_month = periods.max()
    display_yoy = yoy.loc[periods >= last_month - 36]
    frame = pd.DataFrame(
        {
            f"{column}同比": display_yoy[column]
            for column in credit_columns
        }
    )
    figure, axis = _common_line_setup(
        frame,
        PRIVATE_CREDIT_SERIES,
        title=title,
        source_text=source_text,
        ytitle="同比（%）",
    )
    axis.axhline(0, color="#6B7280", linewidth=0.8, zorder=0)
    return figure


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
