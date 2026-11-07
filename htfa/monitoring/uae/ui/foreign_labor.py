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
from htfa.monitoring.uae.contracts.foreign_labor import NEPAL_LABEL
from htfa.monitoring.uae.contracts.foreign_labor import BANGLADESH_LABEL
from htfa.monitoring.uae.processing.foreign_labor import display_foreign_labor_values


def build_foreign_labor_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """用 Ts 默认模板绘制尼泊尔与孟加拉国月度劳工人数（双柱、分居左右轴）。"""
    frame = display_foreign_labor_values(values)
    axis_units = {NEPAL_LABEL: "人", BANGLADESH_LABEL: "人"}
    if units is not None:
        axis_units.update(units)
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups={NEPAL_LABEL: "left", BANGLADESH_LABEL: "right"},
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        bar_series=[NEPAL_LABEL, BANGLADESH_LABEL],
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
