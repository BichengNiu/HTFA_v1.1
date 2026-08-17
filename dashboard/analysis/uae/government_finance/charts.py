"""Plot government and government-controlled enterprise loan year-on-year trends."""

from __future__ import annotations

from matplotlib.figure import Figure
import pandas as pd
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.government_finance.data import (
    GOVERNMENT_CREDIT,
    GRE_CREDIT,
    calculate_calendar_yoy,
)
from dashboard.analysis.uae.plot_helpers import (
    WAR_LINE_COLOR,
    add_bottom_legend,
    WAR_START_DATE,
    add_source_note,
    annotate_war,
    finish_dual_axis_figure,
    matching_line_handles,
    normalize_ts_axis,
)


GOVERNMENT_LINE_COLOR = "#000000"
GRE_LINE_COLOR = "#1F4E79"

YOY_SERIES = (
    (
        GOVERNMENT_CREDIT,
        "政府贷款增长率",
        GOVERNMENT_LINE_COLOR,
        "-",
    ),
    (
        GRE_CREDIT,
        "政府控制企业贷款增长率",
        GRE_LINE_COLOR,
        "--",
    ),
)


def build_government_finance_yoy_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """Plot 政府贷款 / 政府控制企业贷款 作为月度同比增长率（不加总）。"""

    selected = (
        values[[GOVERNMENT_CREDIT, GRE_CREDIT]].dropna(how="all").sort_index()
    )
    if selected.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    yoy = calculate_calendar_yoy(selected).reindex(selected.index)
    periods = pd.PeriodIndex(pd.DatetimeIndex(selected.index), freq="M")
    last_month = periods.max()
    display_mask = periods >= last_month - 36
    yoy = yoy.loc[display_mask]

    frame = pd.DataFrame({spec[1]: yoy[spec[0]] for spec in YOY_SERIES})
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        title=title,
        xtitle="",
        ytitle="同比（%）",
        ytitle_position="side",
        colors=[spec[2] for spec in YOY_SERIES],
        linewidth=2.2,
        markersize=0,
        max_ticks=8,
        year_ruler=True,
        vlines=WAR_START_DATE,
        vline_color=WAR_LINE_COLOR,
        vline_linestyle="--",
        vline_linewidth=1.5,
        show_legend=False,
        note=None,
        grid=True,
        title_loc="center",
        title_pad=14,
    )
    axis = normalize_ts_axis(returned_axis)
    axis.title.set_fontweight("normal")
    axis.axhline(0, color="#6B7280", linewidth=0.8, zorder=0)
    axis.set_ylabel("同比（%）", fontsize=12)
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color("#6B7280")
        spine.set_linewidth(0.9)
    annotate_war(axis)
    add_bottom_legend(
        figure,
        matching_line_handles(axis, [spec[1] for spec in YOY_SERIES]),
        [spec[1] for spec in YOY_SERIES],
        ncol=len(YOY_SERIES),
    )
    finish_dual_axis_figure(figure, top=0.90)
    add_source_note(figure, source_text)
    return figure


__all__ = ["YOY_SERIES", "build_government_finance_yoy_figure"]
