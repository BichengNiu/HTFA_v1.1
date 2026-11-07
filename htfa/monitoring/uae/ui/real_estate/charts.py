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
from Ts.TsPlots.style import GRAY
from htfa.monitoring.uae.contracts.real_estate.charts import COUNT_LABEL
from htfa.monitoring.uae.contracts.real_estate.charts import AMOUNT_LABEL
from htfa.monitoring.uae.processing.real_estate.charts import sales_display_values


def build_sales_figure(
    values: pd.DataFrame,
    *,
    market: str,
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制四个交易类型与用途分市场的笔数柱和金额折线。"""
    frame = sales_display_values(values, market=market, last_month=last_month)[
        [COUNT_LABEL, AMOUNT_LABEL]
    ]
    if frame[COUNT_LABEL].dropna().empty:
        raise ValueError(f"{title}没有可绘制的有效笔数")
    if frame[AMOUNT_LABEL].dropna().empty:
        raise ValueError(f"{title}没有可绘制的有效金额")
    axis_units = {COUNT_LABEL: "笔", AMOUNT_LABEL: "亿迪拉姆"}
    if units is not None:
        axis_units.update(units)
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups={COUNT_LABEL: "left", AMOUNT_LABEL: "right"},
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        bar_series=[COUNT_LABEL],
        bar_face_color=GRAY,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
        units=axis_units,
    )
    count_axis = normalize_ts_axis(returned_axis)
    count_axis.set_ylim(bottom=0)
    count_axis.right_ax.set_ylim(bottom=0)
    annotate_war(count_axis)
    apply_htfa_fonts(figure)
    return figure
