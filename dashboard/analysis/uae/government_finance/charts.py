"""Plot government and government-related entity monthly year-on-year trends."""

from __future__ import annotations

from matplotlib.figure import Figure
import pandas as pd
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.government_finance.data import (
    GOVERNMENT_AND_STATE_CAPITAL_CREDIT,
    GOVERNMENT_AND_STATE_CAPITAL_DEPOSITS,
    calculate_calendar_yoy,
    combine_government_and_state_capital,
)
from dashboard.analysis.uae.oil.charts import (
    CHINESE_FONT_FAMILY,
    _add_source_note,
    _apply_strict_month_ticks,
    _finish_dual_axis_figure,
    _new_ts_figure_axis,
    _normalize_ts_axis,
)


DEPOSIT_LINE_COLOR = "#000000"
CREDIT_LINE_COLOR = "#1F4E79"

YOY_SERIES = (
    (
        GOVERNMENT_AND_STATE_CAPITAL_DEPOSITS,
        "政府及国有资本存款同比",
        DEPOSIT_LINE_COLOR,
        "-",
    ),
    (
        GOVERNMENT_AND_STATE_CAPITAL_CREDIT,
        "政府及国有资本信贷同比",
        CREDIT_LINE_COLOR,
        "--",
    ),
)


def build_government_finance_yoy_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """Plot the four CBUAE series as monthly year-on-year growth rates."""

    selected = combine_government_and_state_capital(values).dropna(how="all")
    selected = selected.sort_index()
    if selected.empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    yoy = calculate_calendar_yoy(selected).reindex(selected.index)
    periods = pd.PeriodIndex(pd.DatetimeIndex(selected.index), freq="M")
    last_month = periods.max()
    display_mask = periods >= last_month - 36
    yoy = yoy.loc[display_mask]

    figure, axis = _new_ts_figure_axis()
    for index, (column, label, color, linestyle) in enumerate(YOY_SERIES):
        figure, returned_axis = plot_series(
            yoy[column].rename(label),
            title=None,
            xtitle="",
            ytitle="同比（%）",
            colors=[color],
            linewidth=2.2,
            markersize=0,
            max_ticks=8,
            freq="month",
            show_legend=False,
            note=None,
            grid=index == len(YOY_SERIES) - 1,
            ax=axis,
        )
        axis = _normalize_ts_axis(returned_axis)
        axis.get_lines()[-1].set_linestyle(linestyle)

    axis.set_title(title, fontsize=14, pad=14)
    axis.xaxis.grid(False)
    axis.axhline(0, color="#6B7280", linewidth=0.8, zorder=0)
    axis.set_ylabel("同比（%）", fontsize=12)
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color("#6B7280")
        spine.set_linewidth(0.9)
    _apply_strict_month_ticks(axis, yoy.index)
    figure.legend(
        handles=axis.get_lines()[: len(YOY_SERIES)],
        labels=[spec[1] for spec in YOY_SERIES],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.115),
        frameon=False,
        prop={"family": CHINESE_FONT_FAMILY[0], "size": 10},
        ncol=len(YOY_SERIES),
    )
    _finish_dual_axis_figure(figure, top=0.90)
    _add_source_note(figure, source_text)
    return figure


__all__ = ["YOY_SERIES", "build_government_finance_yoy_figure"]
