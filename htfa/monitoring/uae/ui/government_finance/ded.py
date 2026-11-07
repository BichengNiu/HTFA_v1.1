from __future__ import annotations
from collections.abc import Mapping
import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series
from htfa.monitoring.uae.processing.periods import within_month_window
from htfa.monitoring.uae.ui.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
)
from htfa.monitoring.uae.processing.sources import source_note
from Ts.TsPlots.style import GRAY
from htfa.monitoring.uae.contracts.government_finance.ded import LICENCES_DISPLAY


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
        values, first_month=last_month - 36, last_month=last_month
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
        ax=create_report_axis(),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure
