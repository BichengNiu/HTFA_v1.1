"""使用 Ts 绘制阿联酋 V2 油价、产量和石油收入时间序列。"""

from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
from Ts.TsPlots import plot_series
from Ts.TsPlots.style import apply_fonts

from dashboard.analysis.uae.oil.alignment import common_latest_month, through_month
from dashboard.analysis.uae.oil.revenue import (
    PRICE_CONTRIBUTION_COLUMN,
    PRODUCTION_CONTRIBUTION_COLUMN,
    REVENUE_COLUMN,
    YOY_COLUMN,
)


MARKET_PRICE_LABEL = "布伦特原油现货价（左轴）"
MARKET_PRODUCTION_LABEL = "阿联酋原油产量（右轴）"
MARKET_RIG_COUNT_LABEL = "阿联酋石油活跃钻机数（外右轴）"
REVENUE_LABEL = "石油收入（左轴）"
REVENUE_YOY_LABEL = "石油收入同比增速（右轴）"
PRICE_CONTRIBUTION_LABEL = "油价拉动率（右轴）"
PRODUCTION_CONTRIBUTION_LABEL = "产量拉动率（右轴）"

PRICE_COLOR = "#000000"
RIG_COUNT_COLOR = "#1F4E79"
BAR_COLOR = "#B8BDC6"
BAR_EDGE_COLOR = "#6B7280"
REVENUE_BAR_COLOR = "#B8BDC6"
REVENUE_BAR_EDGE_COLOR = "#6B7280"
CONTRIBUTION_COLORS = ("#000000", "#000000", "#1F4E79")
CONTRIBUTION_LINESTYLES = ("-", "--", ":")
CHINESE_FONT_FAMILY = ["SimHei", "Microsoft YaHei"]
BOTTOM_LEGEND_Y = 0.115
SOURCE_NOTE_Y = 0.025


def _normalize_ts_axis(axis: Axes | np.ndarray) -> Axes:
    """Return the first scalar axes from supported Ts return shapes."""

    if isinstance(axis, Axes):
        return axis
    if isinstance(axis, np.ndarray):
        for candidate in axis.flat:
            if isinstance(candidate, Axes):
                return candidate
    raise TypeError("Ts plot_series did not return a Matplotlib Axes object")


def _source_note(source_text: str) -> str:
    return f"数据来源：{source_text}"


def _add_source_note(figure: Figure, source_text: str) -> None:
    """Place the source consistently inside the lower-left figure margin."""

    figure.text(
        0.04,
        SOURCE_NOTE_Y,
        _source_note(source_text),
        ha="left",
        va="bottom",
        fontsize=9.5,
        color="#222222",
        fontfamily=CHINESE_FONT_FAMILY,
        clip_on=False,
    )


def _new_ts_figure_axis() -> tuple[Figure, Axes]:
    """Create a scalar axes so Ts cannot split a multi-series chart."""

    apply_fonts()
    figure = Figure(figsize=(9.4, 6.2), dpi=120)
    return figure, figure.add_subplot(111)


def _apply_strict_month_ticks(
    axis: Axes,
    index: pd.Index,
) -> None:
    """绘制月份刻度和年度范围线，只包含真实数据月份。"""

    periods = (
        pd.PeriodIndex(pd.DatetimeIndex(index), freq="M")
        .unique()
        .sort_values()
    )
    if periods.empty:
        return
    tick_periods = periods[periods.month % 3 == 0]
    tick_dates = tick_periods.to_timestamp(how="end").normalize()
    axis.set_xticks(tick_dates)
    axis.set_xticklabels(
        [f"{period.month}月" for period in tick_periods],
        rotation=0,
        ha="center",
        fontsize=9,
    )
    axis.tick_params(axis="x", pad=5)

    year_line_y = -0.18
    cap_height = 0.018
    xaxis_transform = axis.get_xaxis_transform()
    for year in periods.year.unique():
        year_periods = periods[periods.year == year]
        start_date = year_periods[0].to_timestamp(how="end").normalize()
        end_date = year_periods[-1].to_timestamp(how="end").normalize()
        middle_date = start_date + (end_date - start_date) / 2
        axis.hlines(
            year_line_y,
            start_date,
            end_date,
            color="#555555",
            linewidth=0.8,
            transform=xaxis_transform,
            clip_on=False,
        )
        axis.vlines(
            [start_date, end_date],
            year_line_y - cap_height,
            year_line_y + cap_height,
            color="#555555",
            linewidth=0.8,
            transform=xaxis_transform,
            clip_on=False,
        )
        axis.text(
            middle_date,
            year_line_y,
            f" {year}年 ",
            ha="center",
            va="center",
            fontsize=9,
            color="#333333",
            fontfamily=CHINESE_FONT_FAMILY,
            backgroundcolor="white",
            transform=xaxis_transform,
            clip_on=False,
        )
    first_date = periods[0].to_timestamp(how="start").normalize()
    last_date = periods[-1].to_timestamp(how="end").normalize()
    axis.set_xlim(
        first_date - pd.Timedelta(days=10),
        last_date + pd.Timedelta(days=10),
    )


def _finish_dual_axis_figure(
    figure: Figure,
    *,
    top: float,
    right: float = 0.895,
) -> None:
    """统一双轴图在 Streamlit 双栏中的尺寸和留白。"""

    figure.set_size_inches(9.4, 6.2, forward=True)
    figure.subplots_adjust(
        left=0.105,
        right=right,
        bottom=0.30,
        top=top,
    )
    for axis in figure.axes:
        axis.tick_params(axis="both", labelsize=10.5)
        axis.xaxis.label.set_fontfamily(CHINESE_FONT_FAMILY)
        axis.yaxis.label.set_fontfamily(CHINESE_FONT_FAMILY)
        for label in (*axis.get_xticklabels(), *axis.get_yticklabels()):
            label.set_fontfamily(CHINESE_FONT_FAMILY)


def build_oil_market_figure(
    prices: pd.DataFrame,
    production: pd.Series,
    source_text: str,
    rig_count: pd.Series | None = None,
) -> Figure:
    """构建油价、原油产量和阿联酋石油活跃钻机数的月度图。"""

    brent_spot = prices["布伦特现货"].dropna().sort_index().rename(
        MARKET_PRICE_LABEL
    )
    ten_thousand_bpd = production.dropna().sort_index().div(10_000)
    rigs = (
        None
        if rig_count is None or rig_count.dropna().empty
        else rig_count.dropna().sort_index()
    )
    cutoff_series = [
        (MARKET_PRICE_LABEL, brent_spot),
        (MARKET_PRODUCTION_LABEL, ten_thousand_bpd),
    ]
    if rigs is not None:
        cutoff_series.append((MARKET_RIG_COUNT_LABEL, rigs))
    last_month = common_latest_month(cutoff_series)
    brent_spot = through_month(brent_spot, last_month)
    ten_thousand_bpd = through_month(ten_thousand_bpd, last_month)
    if rigs is not None:
        rigs = through_month(rigs, last_month)

    figure, price_axis = _new_ts_figure_axis()
    figure, price_axis = plot_series(
        brent_spot,
        title=None,
        xtitle="",
        ytitle="美元/桶",
        colors=[PRICE_COLOR],
        linewidth=2.2,
        markersize=0,
        max_ticks=8,
        freq="month",
        show_legend=False,
        title_loc="center",
        note=None,
        grid=True,
        ax=price_axis,
    )
    price_axis = _normalize_ts_axis(price_axis)
    price_axis.get_lines()[-1].set_linestyle("--")
    price_axis.set_title(
        "原油价格、产量与钻机数",
        fontsize=14,
        pad=14,
    )
    price_axis.xaxis.grid(False)

    production_axis = price_axis.twinx()
    production_axis.bar(
        ten_thousand_bpd.index,
        ten_thousand_bpd,
        width=20,
        color=BAR_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.6,
        alpha=0.72,
        zorder=1,
    )
    production_axis.set_ylabel("万桶/天", fontsize=12)
    production_axis.set_ylim(bottom=0)
    production_axis.grid(False)
    production_axis.patch.set_visible(False)
    production_axis.tick_params(
        axis="y",
        left=False,
        labelleft=False,
        right=True,
        labelright=True,
    )
    price_axis.tick_params(
        axis="y",
        left=True,
        labelleft=True,
        right=False,
        labelright=False,
    )
    price_axis.set_zorder(2)
    production_axis.set_zorder(1)
    price_axis.patch.set_visible(False)

    rig_axis: Axes | None = None
    if rigs is not None:
        rig_axis = price_axis.twinx()
        rig_axis.spines["right"].set_position(("outward", 52))
        rig_axis.plot(
            rigs.index,
            rigs,
            color=RIG_COUNT_COLOR,
            linewidth=2.2,
            linestyle="-",
            label=MARKET_RIG_COUNT_LABEL,
            zorder=4,
        )
        rig_axis.set_ylabel("活跃钻机数（台）", fontsize=12, color=RIG_COUNT_COLOR)
        rig_axis.grid(False)
        rig_axis.patch.set_visible(False)
        rig_axis.tick_params(
            axis="y",
            left=False,
            labelleft=False,
            right=True,
            labelright=True,
            colors=RIG_COUNT_COLOR,
        )
        rig_axis.spines["right"].set_color(RIG_COUNT_COLOR)
        rig_axis.set_zorder(3)

    display_index = brent_spot.index.union(ten_thousand_bpd.index)
    if rigs is not None:
        display_index = display_index.union(rigs.index)
    _apply_strict_month_ticks(price_axis, display_index)

    price_swatch = Line2D(
        [0.06, 0.10],
        [BOTTOM_LEGEND_Y, BOTTOM_LEGEND_Y],
        transform=figure.transFigure,
        color=PRICE_COLOR,
        linewidth=2.2,
        linestyle="--",
        zorder=20,
    )
    production_swatch = Rectangle(
        (0.405, BOTTOM_LEGEND_Y - 0.012),
        0.035,
        0.024,
        transform=figure.transFigure,
        facecolor=BAR_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.8,
        zorder=20,
    )
    figure.add_artist(price_swatch)
    figure.add_artist(production_swatch)
    figure.text(
        0.11,
        BOTTOM_LEGEND_Y,
        MARKET_PRICE_LABEL,
        ha="left",
        va="center",
        fontsize=10.5,
        fontfamily=CHINESE_FONT_FAMILY,
        clip_on=False,
        zorder=21,
    )
    figure.text(
        0.45,
        BOTTOM_LEGEND_Y,
        MARKET_PRODUCTION_LABEL,
        ha="left",
        va="center",
        fontsize=10.5,
        fontfamily=CHINESE_FONT_FAMILY,
        clip_on=False,
        zorder=21,
    )
    if rig_axis is not None:
        rig_swatch = Line2D(
            [0.72, 0.76],
            [BOTTOM_LEGEND_Y, BOTTOM_LEGEND_Y],
            transform=figure.transFigure,
            color=RIG_COUNT_COLOR,
            linewidth=2.2,
            linestyle="-",
            zorder=20,
        )
        figure.add_artist(rig_swatch)
        figure.text(
            0.77,
            BOTTOM_LEGEND_Y,
            MARKET_RIG_COUNT_LABEL,
            ha="left",
            va="center",
            fontsize=10.5,
            fontfamily=CHINESE_FONT_FAMILY,
            clip_on=False,
            zorder=21,
        )
    price_axis.set_ylabel("美元/桶", fontsize=12)
    _finish_dual_axis_figure(
        figure,
        top=0.91,
        right=0.83 if rig_axis is not None else 0.895,
    )
    _add_source_note(figure, source_text)
    return figure


def build_oil_revenue_figure(
    revenue: pd.DataFrame,
    source_text: str,
) -> Figure:
    """使用 Ts 构建收入柱和同比、价格及产量拉动率曲线。"""

    rate_specs = (
        (YOY_COLUMN, REVENUE_YOY_LABEL),
        (PRICE_CONTRIBUTION_COLUMN, PRICE_CONTRIBUTION_LABEL),
        (PRODUCTION_CONTRIBUTION_COLUMN, PRODUCTION_CONTRIBUTION_LABEL),
    )
    cutoff_series = [(REVENUE_LABEL, revenue[REVENUE_COLUMN])]
    cutoff_series.extend(
        (label, revenue[column])
        for column, label in rate_specs
        if not revenue[column].dropna().empty
    )
    last_month = common_latest_month(cutoff_series)
    revenue = through_month(revenue, last_month)
    figure, rate_axis = _new_ts_figure_axis()
    for index, ((column, label), color, linestyle) in enumerate(
        zip(
            rate_specs,
            CONTRIBUTION_COLORS,
            CONTRIBUTION_LINESTYLES,
            strict=True,
        )
    ):
        figure, returned_axis = plot_series(
            revenue[column].rename(label),
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
            grid=index == len(rate_specs) - 1,
            ax=rate_axis,
        )
        rate_axis = _normalize_ts_axis(returned_axis)
        rate_axis.get_lines()[-1].set_linestyle(linestyle)

    rate_axis.set_title(
        "估算石油收入",
        fontsize=14,
        pad=14,
    )
    rate_axis.xaxis.grid(False)
    revenue_axis = rate_axis.twinx()
    revenue_axis.bar(
        revenue.index,
        revenue[REVENUE_COLUMN],
        width=20,
        color=REVENUE_BAR_COLOR,
        edgecolor=REVENUE_BAR_EDGE_COLOR,
        linewidth=0.6,
        alpha=0.72,
        zorder=1,
    )
    revenue_axis.set_ylabel("亿美元", fontsize=12)
    revenue_axis.set_ylim(bottom=0)
    revenue_axis.yaxis.tick_left()
    revenue_axis.yaxis.set_label_position("left")
    revenue_axis.spines["left"].set_visible(True)
    revenue_axis.spines["right"].set_visible(False)
    revenue_axis.grid(False)
    revenue_axis.patch.set_visible(False)
    revenue_axis.tick_params(
        axis="y",
        left=True,
        labelleft=True,
        right=False,
        labelright=False,
    )
    rate_axis.yaxis.tick_right()
    rate_axis.yaxis.set_label_position("right")
    rate_axis.set_ylabel("拉动率/同比（%）", fontsize=12)
    rate_axis.spines["right"].set_visible(True)
    rate_axis.spines["left"].set_visible(False)
    rate_axis.tick_params(
        axis="y",
        left=False,
        labelleft=False,
        right=True,
        labelright=True,
    )
    rate_axis.set_zorder(2)
    revenue_axis.set_zorder(1)
    rate_axis.patch.set_visible(False)
    _apply_strict_month_ticks(rate_axis, revenue.index)

    revenue_handle = Patch(
        facecolor=REVENUE_BAR_COLOR,
        edgecolor=REVENUE_BAR_EDGE_COLOR,
        label=REVENUE_LABEL,
    )
    rate_lines = rate_axis.get_lines()
    figure.legend(
        handles=[revenue_handle, *rate_lines],
        labels=[
            REVENUE_LABEL,
            REVENUE_YOY_LABEL,
            PRICE_CONTRIBUTION_LABEL,
            PRODUCTION_CONTRIBUTION_LABEL,
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.115),
        frameon=False,
        prop={"family": "SimHei", "size": 10},
        ncol=2,
    )
    _finish_dual_axis_figure(figure, top=0.90)
    _add_source_note(figure, source_text)
    return figure


__all__ = [
    "build_oil_market_figure",
    "build_oil_revenue_figure",
]
