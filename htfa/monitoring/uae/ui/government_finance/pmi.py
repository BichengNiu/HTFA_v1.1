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
from htfa.monitoring.uae.contracts.government_finance.pmi import PMI_LABEL
from htfa.monitoring.uae.processing.government_finance.pmi import display_pmi_values


def build_pmi_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制阿联酋非油私营部门 PMI 的月度线图。"""
    display_values = display_pmi_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    axis_units = {PMI_LABEL: "点"}
    if units is not None:
        axis_units.update(units)
    figure, returned_axis = plot_series(
        display_values[PMI_LABEL].rename(PMI_LABEL),
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=False,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure
