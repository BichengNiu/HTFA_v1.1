"""阿联酋 1 年期 EIBOR 与美国有效联邦基金利率的月度均值对比图。

两条序列都存放在用户维护的 ``日度_Wind`` sheet 中：EIBOR 为日度、EFFR 实为逐日
取值（sheet 元数据标注月频），统一先按自然月 ``resample`` 取均值，再绘制双线水平
（单位 %），与「财政支出和投资」区块其它图对齐到同一 3 年窗口。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    open_uae_workbook,
    parse_target_sheet,
)


RATES_SHEET = "日度_Wind"

EIBOR_OVERNIGHT_DISPLAY = "阿联酋银行间市场拆借利率（隔夜）"
EIBOR_ONEYEAR_DISPLAY = "阿联酋银行间市场拆借利率（1年期）"
US_OVERNIGHT_DISPLAY = "美国银行间市场拆借利率（隔夜）"
US_SOFR_12M_DISPLAY = "美国银行间市场拆借利率（1年期）"
EIBOR_OVERNIGHT_INDICATOR = "阿联酋:银行间同业拆借利率(EIBOR):隔夜"
EIBOR_ONEYEAR_INDICATOR = "阿联酋:银行间同业拆借利率(EIBOR):1年"
US_OVERNIGHT_INDICATOR = "美国:有效联邦基金利率(EFFR)"
US_SOFR_12M_INDICATOR = "美国:SOFR期限利率:12个月"

RATES_INDICATORS: tuple[tuple[str, str], ...] = (
    (EIBOR_OVERNIGHT_DISPLAY, EIBOR_OVERNIGHT_INDICATOR),
    (EIBOR_ONEYEAR_DISPLAY, EIBOR_ONEYEAR_INDICATOR),
    (US_OVERNIGHT_DISPLAY, US_OVERNIGHT_INDICATOR),
    (US_SOFR_12M_DISPLAY, US_SOFR_12M_INDICATOR),
)

# 序列名即图例文本；颜色与线型由模板色板/循环接管。
RATES_SERIES = (
    EIBOR_OVERNIGHT_DISPLAY,
    EIBOR_ONEYEAR_DISPLAY,
    US_OVERNIGHT_DISPLAY,
    US_SOFR_12M_DISPLAY,
)

ALLOWED_FREQUENCIES = {"日", "日度", "月", "月度"}


@dataclass(frozen=True)
class RatesData:
    """EIBOR 与美国的隔夜/1年期市场利率的月度均值数据与元数据。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_rates_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> RatesData:
    """读 ``日度_Wind`` 的四条利率并聚合成月度均值。"""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        frame, metadata = parse_target_sheet(
            excel_file,
            sheet_name=RATES_SHEET,
            targets=RATES_INDICATORS,
            allowed_frequencies=ALLOWED_FREQUENCIES,
            expected_unit="%",
        )
    monthly = frame.resample("ME").mean()
    monthly = monthly.dropna(how="all").sort_index()
    if monthly.empty:
        raise ValueError(f"{RATES_SHEET} 没有可用的利率观测")
    return RatesData(
        values=monthly,
        metadata=metadata,
        source_name=source_name,
    )


def build_rates_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制阿联酋与美国隔夜/1年期利率的月度均值四线图（单位 %），内部取最近 36 个月。"""

    selected = values.dropna(how="all").sort_index()
    if selected.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    periods = pd.PeriodIndex(pd.DatetimeIndex(selected.index), freq="M")
    last_month = periods.max()
    display_values = selected.loc[periods >= last_month - 36]
    frame = pd.DataFrame({name: display_values[name] for name in RATES_SERIES})
    axis_units = {name: "%" for name in RATES_SERIES}
    if units is not None:
        axis_units.update(units)
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
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "EIBOR_ONEYEAR_DISPLAY",
    "EIBOR_ONEYEAR_INDICATOR",
    "EIBOR_OVERNIGHT_DISPLAY",
    "EIBOR_OVERNIGHT_INDICATOR",
    "RATES_INDICATORS",
    "RATES_SERIES",
    "RATES_SHEET",
    "RatesData",
    "US_OVERNIGHT_DISPLAY",
    "US_OVERNIGHT_INDICATOR",
    "US_SOFR_12M_DISPLAY",
    "US_SOFR_12M_INDICATOR",
    "build_rates_figure",
    "load_rates_data",
]
