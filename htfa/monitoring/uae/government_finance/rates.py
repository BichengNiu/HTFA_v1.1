"""阿联酋央行 EIBOR 隔夜/1年与纽约联储 EFFR 的月度均值。

日度数据经 DuckDB 写入工作簿。三条序列按自然月平均，截到共同的最新
完整月份；纽约联储不发布 12 个月 Term SOFR，该旧列不用于本报告。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.database import PublishedUAEData, require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.monitoring.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
    translate_source_text,
)
from htfa.monitoring.uae.periods import through_last_complete_month
from htfa.data.economic_workbook import SheetSeriesMetadata


RATES_SHEET = "日度_Wind"

EIBOR_OVERNIGHT_DISPLAY = "阿联酋银行间市场拆借利率（隔夜）"
EIBOR_ONEYEAR_DISPLAY = "阿联酋银行间市场拆借利率（1年期）"
US_OVERNIGHT_DISPLAY = "美国银行间市场拆借利率（隔夜）"
EIBOR_OVERNIGHT_INDICATOR = "阿联酋:银行间同业拆借利率(EIBOR):隔夜"
EIBOR_ONEYEAR_INDICATOR = "阿联酋:银行间同业拆借利率(EIBOR):1年"
US_OVERNIGHT_INDICATOR = "美国:有效联邦基金利率(EFFR)"

RATES_INDICATORS: tuple[tuple[str, str], ...] = (
    (EIBOR_OVERNIGHT_DISPLAY, EIBOR_OVERNIGHT_INDICATOR),
    (EIBOR_ONEYEAR_DISPLAY, EIBOR_ONEYEAR_INDICATOR),
    (US_OVERNIGHT_DISPLAY, US_OVERNIGHT_INDICATOR),
)

# 序列名即图例文本；颜色与线型由模板色板/循环接管。
RATES_SERIES = (
    EIBOR_OVERNIGHT_DISPLAY,
    EIBOR_ONEYEAR_DISPLAY,
    US_OVERNIGHT_DISPLAY,
)

ALLOWED_FREQUENCIES = {"日", "日度", "月", "月度"}


@dataclass(frozen=True)
class RatesData:
    """EIBOR 隔夜/1年与美国 EFFR 的月度均值数据与元数据。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]


def load_rates_data(
    source: PublishedUAEData,
) -> RatesData:
    """读取三条官方利率，聚合为月度均值并统一末期。"""

    source = require_published_source(source)
    with source.open() as tables:
        frame, metadata = parse_target_sheet(
            tables,
            sheet_name=RATES_SHEET,
            targets=RATES_INDICATORS,
            allowed_frequencies=ALLOWED_FREQUENCIES,
            expected_unit="%",
        )
    for label, _ in RATES_INDICATORS:
        expected_source = (
            "美联储纽约分行" if label == US_OVERNIGHT_DISPLAY else "阿联酋央行"
        )
        if translate_source_text(metadata[label].source) != expected_source:
            raise ValueError(f"{label}须使用{expected_source}数据，请更新数据库报告")
    monthly = pd.DataFrame(
        {
            label: through_last_complete_month(frame[label]).resample("ME").mean()
            for label, _ in RATES_INDICATORS
        }
    )
    monthly = monthly.dropna(how="all").sort_index()
    common = monthly.dropna(how="any")
    if common.empty:
        raise ValueError(f"{RATES_SHEET} 没有共同可用的完整月份利率观测")
    monthly = monthly.loc[:common.index.max()]
    return RatesData(
        values=monthly,
        metadata=metadata,
    )


def build_rates_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制三条官方利率的月度均值（单位 %），取最近 36 个月。"""

    selected = through_last_complete_month(values).dropna(how="all").sort_index()
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
    "build_rates_figure",
    "load_rates_data",
]
