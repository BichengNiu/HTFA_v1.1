"""使用 Ts 绘制阿联酋 V2 油价、产量和石油收入时间序列。"""

from __future__ import annotations

from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.patches import Rectangle
import pandas as pd
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.oil.alignment import common_latest_month, through_month
from dashboard.analysis.uae.oil.revenue import (
    PRICE_COLUMN,
    REVENUE_COLUMN,
)
from dashboard.analysis.uae.plot_helpers import (
    CHINESE_FONT_FAMILY,
    WAR_LINE_COLOR,
    WAR_START_DATE,
    add_source_note,
    finish_dual_axis_figure,
    normalize_ts_axis,
)


MARKET_PRODUCTION_LABEL = "阿联酋原油产量（左轴）"
MARKET_RIG_COUNT_LABEL = "阿联酋石油活跃钻机数（右轴）"
REVENUE_LABEL = "石油收入（右轴）"
REVENUE_PRICE_LABEL = "布伦特原油现货价（左轴）"

PRICE_COLOR = "#000000"
RIG_COUNT_COLOR = "#1F4E79"
BAR_COLOR = "#B8BDC6"
BAR_EDGE_COLOR = "#6B7280"
REVENUE_BAR_COLOR = "#B8BDC6"
REVENUE_BAR_EDGE_COLOR = "#6B7280"
BOTTOM_LEGEND_Y = 0.115


def _restore_visible_spines(figure: Figure) -> None:
    """Ts 的 style_axes 隐藏上/右脊线；本项目双轴图保持四边可见。"""

    for axis in figure.axes:
        for spine in axis.spines.values():
            spine.set_visible(True)


def build_oil_market_figure(
    production: pd.Series,
    source_text: str,
    rig_count: pd.Series | None = None,
) -> Figure:
    """构建阿联酋原油产量和石油活跃钻机数的月度图。"""

    ten_thousand_bpd = production.dropna().sort_index().div(10_000)
    rigs = (
        None
        if rig_count is None or rig_count.dropna().empty
        else rig_count.dropna().sort_index()
    )
    cutoff_series = [(MARKET_PRODUCTION_LABEL, ten_thousand_bpd)]
    if rigs is not None:
        cutoff_series.append((MARKET_RIG_COUNT_LABEL, rigs))
    last_month = common_latest_month(cutoff_series)
    ten_thousand_bpd = through_month(ten_thousand_bpd, last_month)
    if rigs is not None:
        rigs = through_month(rigs, last_month)

    frame = pd.DataFrame({MARKET_PRODUCTION_LABEL: ten_thousand_bpd})
    axis_groups = {MARKET_PRODUCTION_LABEL: "left"}
    colors = [BAR_COLOR]
    if rigs is not None:
        frame[MARKET_RIG_COUNT_LABEL] = rigs
        axis_groups[MARKET_RIG_COUNT_LABEL] = "right"
        colors.append(RIG_COUNT_COLOR)
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups=axis_groups,
        title="原油产量及活动钻机数",
        xtitle="",
        ytitle="万桶/天",
        colors=colors,
        linewidth=2.2,
        markersize=0,
        max_ticks=8,
        freq="month",
        year_ruler=True,
        bar_series=[MARKET_PRODUCTION_LABEL],
        bar_edge_color=BAR_EDGE_COLOR,
        bar_edge_linewidth=0.6,
        bar_alpha=0.72,
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
    production_axis = normalize_ts_axis(returned_axis)
    production_axis.title.set_fontweight("normal")

    rig_axis: Axes | None = None
    if rigs is not None:
        rig_axis = production_axis.right_ax
        rig_axis.get_lines()[0].set_linestyle("-")
        rig_axis.set_ylabel("活跃钻机数（台）", fontsize=12)
        rig_axis.patch.set_visible(False)
        rig_axis.set_zorder(3)
    _restore_visible_spines(figure)

    production_swatch = Rectangle(
        (0.22, BOTTOM_LEGEND_Y - 0.012),
        0.035,
        0.024,
        transform=figure.transFigure,
        facecolor=BAR_COLOR,
        edgecolor=BAR_EDGE_COLOR,
        linewidth=0.8,
        zorder=20,
    )
    figure.add_artist(production_swatch)
    figure.text(
        0.265,
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
            [0.56, 0.60],
            [BOTTOM_LEGEND_Y, BOTTOM_LEGEND_Y],
            transform=figure.transFigure,
            color=RIG_COUNT_COLOR,
            linewidth=2.2,
            linestyle="-",
            zorder=20,
        )
        figure.add_artist(rig_swatch)
        figure.text(
            0.61,
            BOTTOM_LEGEND_Y,
            MARKET_RIG_COUNT_LABEL,
            ha="left",
            va="center",
            fontsize=10.5,
            fontfamily=CHINESE_FONT_FAMILY,
            clip_on=False,
            zorder=21,
        )
    finish_dual_axis_figure(figure, top=0.91)
    add_source_note(figure, source_text)
    return figure


def build_oil_revenue_figure(
    revenue: pd.DataFrame,
    source_text: str,
) -> Figure:
    """布伦特月均价线在左轴，石油收入柱在右轴。"""

    last_month = common_latest_month(
        [(REVENUE_LABEL, revenue[REVENUE_COLUMN])]
    )
    revenue = through_month(revenue, last_month)
    price = revenue[PRICE_COLUMN].rename(REVENUE_PRICE_LABEL)
    frame = pd.DataFrame(
        {REVENUE_PRICE_LABEL: price, REVENUE_LABEL: revenue[REVENUE_COLUMN]}
    )

    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups={
            REVENUE_PRICE_LABEL: "left",
            REVENUE_LABEL: "right",
        },
        title="石油价格与阿联酋石油收入",
        xtitle="",
        ytitle="美元/桶",
        colors=[PRICE_COLOR, REVENUE_BAR_COLOR],
        linewidth=2.2,
        markersize=0,
        max_ticks=8,
        freq="month",
        year_ruler=True,
        bar_series=[REVENUE_LABEL],
        bar_edge_color=REVENUE_BAR_EDGE_COLOR,
        bar_edge_linewidth=0.6,
        bar_alpha=0.72,
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
    price_axis = normalize_ts_axis(returned_axis)
    revenue_axis = price_axis.right_ax
    price_axis.get_lines()[-1].set_linestyle("--")
    price_axis.title.set_fontweight("normal")

    revenue_axis.set_ylabel("亿美元", fontsize=12)
    revenue_axis.patch.set_visible(False)
    price_axis.set_zorder(2)
    revenue_axis.set_zorder(1)
    price_axis.patch.set_visible(False)
    _restore_visible_spines(figure)

    revenue_handle = Patch(
        facecolor=REVENUE_BAR_COLOR,
        edgecolor=REVENUE_BAR_EDGE_COLOR,
        label=REVENUE_LABEL,
    )
    figure.legend(
        handles=[
            *[
                line
                for line in price_axis.get_lines()
                if not line.get_label().startswith("_")
            ],
            revenue_handle,
        ],
        labels=[REVENUE_PRICE_LABEL, REVENUE_LABEL],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.115),
        frameon=False,
        prop={"family": CHINESE_FONT_FAMILY[0], "size": 10},
        ncol=2,
    )
    finish_dual_axis_figure(figure, top=0.90)
    add_source_note(figure, source_text)
    return figure


__all__ = [
    "build_oil_market_figure",
    "build_oil_revenue_figure",
]
