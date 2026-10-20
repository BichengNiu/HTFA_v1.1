"""Plot government and government-controlled enterprise loan year-on-year trends."""

from __future__ import annotations

from collections.abc import Mapping

from matplotlib.figure import Figure
import pandas as pd
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.government_finance.data import (
    GOVERNMENT_CREDIT,
    GRE_CREDIT,
    display_calendar_yoy,
)
from htfa.monitoring.uae.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)


YOY_SERIES = (
    (GOVERNMENT_CREDIT, "政府贷款同比"),
    (GRE_CREDIT, "政府控股企业贷款同比"),
)


def build_government_finance_yoy_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """Plot 政府贷款 / 政府控制企业贷款 作为月度同比增长率（不加总）。"""

    frame = display_calendar_yoy(
        values[[GOVERNMENT_CREDIT, GRE_CREDIT]]
    ).rename(columns=dict(YOY_SERIES))
    if frame.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    axis_units = {spec[1]: "%" for spec in YOY_SERIES}
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
        ax=create_report_axis(),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = ["YOY_SERIES", "build_government_finance_yoy_figure"]
