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
from htfa.monitoring.uae.processing.periods import through_last_complete_month
from htfa.monitoring.uae.contracts.government_finance.rates import RATES_SERIES


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
        ax=create_report_axis(),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure
