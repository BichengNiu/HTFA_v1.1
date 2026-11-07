from __future__ import annotations
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
from htfa.monitoring.uae.contracts.government_finance.search_index import SEARCH_SERIES
from htfa.monitoring.uae.processing.government_finance.search_index import (
    display_search_index_values,
)


def build_search_index_figure(
    values: pd.DataFrame, *, title: str, source_text: str
) -> Figure:
    """两个工作搜索关键词经 Z-score 标准化后在同一坐标轴展示。"""
    display_values = display_search_index_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")
    frame = display_values[[label for _, label in SEARCH_SERIES]]
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        max_ticks=16,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
        units={label: "标准化指数" for _, label in SEARCH_SERIES},
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure
