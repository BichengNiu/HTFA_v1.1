"""DED 迪拜当月新发执照数的月度柱状图。

``月度_DED`` 沿用页面的前六行元数据协议，但两列单位不同（企业“家”、许可“张”），
因此用定制 loader 读取（与 ``foreign_labor`` 的定制解析一致）。图表只展示「当月
新发执照数」（执照号筛重）单条柱，不再叠加「有发证活动企业数」。窗口由调用方给定
（与「财政金融」区块锚定到同一最新月，避开 DED 快照尾部欠计噪声）。
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from dataclasses import dataclass, replace

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
from Ts.TsPlots.style import GRAY


DED_SHEET = "月度_DED"

ENTERPRISES_INDICATOR = "迪拜:当月有发证活动的企业数(企业号筛重)"
LICENCES_INDICATOR = "迪拜:当月新发执照数(执照号筛重)"
ENTERPRISES_DISPLAY = "有发证活动企业数"
LICENCES_DISPLAY = "当月新发执照数"

DED_INDICATORS: tuple[tuple[str, str], ...] = (
    (ENTERPRISES_DISPLAY, ENTERPRISES_INDICATOR),
    (LICENCES_DISPLAY, LICENCES_INDICATOR),
)
EXPECTED_UNITS = {
    ENTERPRISES_DISPLAY: "家",
    LICENCES_DISPLAY: "张",
}


@dataclass(frozen=True)
class DedData:
    """迪拜企业发证活动与新发执照的月度序列及来源信息。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]


def load_ded_data(
    source: PublishedUAEData,
) -> DedData:
    """读取 ``月度_DED`` 的有发证活动企业数与当月新发执照数两列。"""

    source = require_published_source(source)
    with source.open() as tables:
        frame, metadata = parse_target_sheet(
            tables, sheet_name=DED_SHEET, targets=DED_INDICATORS,
            allowed_frequencies={"月"}, expected_unit=EXPECTED_UNITS,
            strict_duplicates=True,
        )
    metadata = {
        name: replace(item, source=_clean_source(item.source))
        for name, item in metadata.items()
    }

    return DedData(
        values=frame,
        metadata=metadata,
    )


def _clean_source(value: str) -> str:
    """去掉来源里的括号及括号内说明（如 "(commerce_number 按发照月去重)"）。"""

    return re.sub(r"[（(][^）)]*[）)]", "", value).strip()


def build_ded_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制当月新发执照数的月度柱状图（窗口 [last_month-36, last_month]，单序列无图例）。"""

    display_values = within_month_window(
        values,
        first_month=last_month - 36,
        last_month=last_month,
    )
    if display_values[LICENCES_DISPLAY].dropna().empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    frame = display_values[[LICENCES_DISPLAY]].dropna(how="all")
    axis_units = {LICENCES_DISPLAY: "张"}
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
        bar_series=[LICENCES_DISPLAY],
        bar_face_color=GRAY,
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
    "DED_INDICATORS",
    "DED_SHEET",
    "DedData",
    "ENTERPRISES_DISPLAY",
    "ENTERPRISES_INDICATOR",
    "LICENCES_DISPLAY",
    "LICENCES_INDICATOR",
    "build_ded_figure",
    "load_ded_data",
]
