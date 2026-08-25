"""使用 Ts 绘制阿联酋 V2 油价、产量和石油收入时间序列。

与 Ts 模板默认对齐，仅保留页面级豁免：``facet=False``（合并单一坐标）、
``ytitle_position="side"``（侧边竖排 y 轴标题）、``year_ruler=True``
（严格月刻度 + 年标尺）、``grid=True``（虚线网格）、微软雅黑字体、
画布 (9.4, 6.2)。序列名为裸变量名，双轴叠加图例的「（左轴/右轴）」
后缀由模板自动追加；图例与图注均交予模板（``show_legend=True`` /
``note``）；战争基准线用模板默认参考色，战争文字标注由
``annotate_war`` 保留。
"""

from __future__ import annotations

from collections.abc import Mapping

from matplotlib.figure import Figure
import pandas as pd
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.oil.alignment import common_latest_month, through_month
from dashboard.analysis.uae.oil.revenue import (
    PRICE_COLUMN,
    REVENUE_COLUMN,
)
from dashboard.analysis.uae.oil.war_pressure import (
    PRESSURE_LABEL,
    RAW_LABELS,
)
from dashboard.analysis.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from Ts.TsPlots.style import DARK_BLUE, DARK_RED, GRAY


MARKET_PRODUCTION_LABEL = "阿联酋原油产量"
MARKET_RIG_COUNT_LABEL = "阿联酋石油活跃钻机数"
REVENUE_LABEL = "石油收入"
REVENUE_PRICE_LABEL = "布伦特原油现货价"


def _annotate_bar_values(
    axis,
    frame: pd.DataFrame,
    labels: tuple[str, ...],
) -> None:
    """在 Ts 柱状序列的柱顶显示原始数值。"""

    for container, label in zip(axis.containers, labels, strict=False):
        series = frame[label].dropna()
        values = [f"{float(value):g}" for value in series]
        axis.bar_label(
            container,
            labels=values,
            padding=2,
            fontsize=8,
            color="#222222",
            zorder=10,
        )


def _annotate_line_values_above(
    axis,
    label: str,
    *,
    decimals: int = 1,
) -> None:
    """在单条线序列的每个数据点正上方显示数值。"""

    line = next(
        (item for item in axis.get_lines() if item.get_label() == label),
        None,
    )
    if line is None:
        return

    for x_value, y_value in zip(line.get_xdata(), line.get_ydata(), strict=False):
        if pd.isna(y_value):
            continue
        axis.annotate(
            f"{float(y_value):.{decimals}f}",
            xy=(x_value, y_value),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            color=line.get_color(),
            zorder=10,
        )


def build_war_pressure_raw_figure(
    values: pd.DataFrame,
    source_text: str,
) -> Figure:
    """构建三类武器原始月度数量图。"""

    frame = values.loc[:, list(RAW_LABELS)].dropna(how="all").sort_index()
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        colors=[DARK_BLUE, GRAY, DARK_RED],
        axis_groups={label: "raw" for label in RAW_LABELS},
        title="袭击手段",
        xtitle="",
        ytitle="数量（枚/架）",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        show_legend=True,
        legend_cols=3,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        bar_series=list(RAW_LABELS),
    )
    axis = normalize_ts_axis(returned_axis)
    _annotate_bar_values(axis, frame, tuple(RAW_LABELS))
    apply_htfa_fonts(figure)
    return figure


def build_war_pressure_index_figure(
    values: pd.DataFrame,
    source_text: str,
) -> Figure:
    """构建三类武器强权重 ``log1p`` 日度和的月度战争压力指数图。"""

    frame = values.loc[:, [PRESSURE_LABEL]].dropna(how="all").sort_index()
    figure, returned_axis = plot_series(
        frame,
        facet=False,
        colors=[DARK_RED],
        title="战争压力指数",
        xtitle="",
        ytitle="指数",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units={PRESSURE_LABEL: "指数"},
    )
    axis = normalize_ts_axis(returned_axis)
    _annotate_line_values_above(axis, PRESSURE_LABEL)
    apply_htfa_fonts(figure)
    return figure


def build_oil_market_figure(
    production: pd.Series,
    source_text: str,
    rig_count: pd.Series | None = None,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """构建阿联酋原油产量和石油活跃钻机数的月度图（Ts 模板）。"""

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
    if rigs is not None:
        frame[MARKET_RIG_COUNT_LABEL] = rigs
        axis_groups[MARKET_RIG_COUNT_LABEL] = "right"

    axis_units = {MARKET_PRODUCTION_LABEL: "万桶/天"}
    if rigs is not None:
        axis_units[MARKET_RIG_COUNT_LABEL] = "台"
    if units is not None:
        axis_units.update(units)

    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups=axis_groups,
        title="原油产量及活动钻机数",
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        bar_series=[MARKET_PRODUCTION_LABEL],
        bar_face_color=GRAY,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    production_axis = normalize_ts_axis(returned_axis)
    annotate_war(production_axis)
    apply_htfa_fonts(figure)
    return figure


def build_oil_revenue_figure(
    revenue: pd.DataFrame,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """布伦特月均价线在左轴，石油收入柱在右轴（Ts 模板）。"""

    last_month = common_latest_month(
        [(REVENUE_LABEL, revenue[REVENUE_COLUMN])]
    )
    revenue = through_month(revenue, last_month)
    price = revenue[PRICE_COLUMN].rename(REVENUE_PRICE_LABEL)
    frame = pd.DataFrame(
        {REVENUE_PRICE_LABEL: price, REVENUE_LABEL: revenue[REVENUE_COLUMN]}
    )
    axis_units = {
        REVENUE_PRICE_LABEL: "美元/桶",
        REVENUE_LABEL: "亿美元",
    }
    if units is not None:
        axis_units.update(units)

    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups={
            REVENUE_PRICE_LABEL: "left",
            REVENUE_LABEL: "right",
        },
        title="石油价格与阿联酋石油收入",
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        bar_series=[REVENUE_LABEL],
        bar_face_color=GRAY,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    price_axis = normalize_ts_axis(returned_axis)
    annotate_war(price_axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "build_war_pressure_index_figure",
    "build_war_pressure_raw_figure",
    "build_oil_market_figure",
    "build_oil_revenue_figure",
]
