"""交通物流月度量价图：霍尔木兹通道 + UAE 港口联动（Ts 默认模板）。

两张图：
- 图1「霍尔木兹海峡月度过境与载货容量」：油轮过境（左轴,艘次）+ 总容量与
  油轮容量（右轴,百万吨）三线，聚焦战争对能源通道的冲击（2026-03 断崖）。
- 图2「UAE 港口到港与霍尔木兹油轮容量联动」：UAE 到港（左轴,艘次）对
  霍尔木兹油轮容量（右轴,百万吨），展示"外因（通道流量）→内果（本国港口）"。

两图按板块锚定月往前 36 个月，红色虚线为 2026 年 3 月美伊战争起始基准线
（模板参考线默认色）。图例/图注由模板托管；字体覆盖为微软雅黑（项目豁免）。
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.oil.alignment import within_month_window
from dashboard.analysis.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from dashboard.analysis.uae.transport.data import (
    HORMUZ_CAPACITY,
    HORMUZ_TANKER_CALLS,
    HORMUZ_TANKER_CAPACITY,
    UAE_PORT_CALLS,
)

# 载货容量在图上统一折算为百万吨（吨 ÷ 1e6），与艘次分居左右轴。
MT_FACTOR = 1_000_000

HORMUZ_CHANNEL_TITLE = "霍尔木兹海峡月度过境与载货容量"
PORT_LINKAGE_TITLE = "UAE 港口到港与霍尔木兹油轮容量联动"

HORMUZ_CALLS_LABEL = HORMUZ_TANKER_CALLS
UAE_CALLS_LABEL = UAE_PORT_CALLS
HORMUZ_CAPACITY_LABEL = HORMUZ_CAPACITY
HORMUZ_TANKER_CAPACITY_LABEL = HORMUZ_TANKER_CAPACITY


def _windowed(
    frame: pd.DataFrame,
    last_month: pd.Period,
) -> pd.DataFrame:
    return within_month_window(
        frame,
        first_month=last_month - 36,
        last_month=last_month,
    ).dropna(how="all")


def build_hormuz_channel_figure(
    values: pd.DataFrame,
    *,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """图1：霍尔木兹油轮过境（左轴）与总/油轮容量（右轴）三线双轴图。"""

    display = _windowed(values, last_month)
    if display[HORMUZ_TANKER_CALLS].dropna().empty:
        raise ValueError(f"{HORMUZ_CHANNEL_TITLE}没有可绘制的过境次数")
    frame = pd.DataFrame(
        {
            HORMUZ_CALLS_LABEL: display[HORMUZ_TANKER_CALLS],
            HORMUZ_CAPACITY_LABEL: display[HORMUZ_CAPACITY] / MT_FACTOR,
            HORMUZ_TANKER_CAPACITY_LABEL: (
                display[HORMUZ_TANKER_CAPACITY] / MT_FACTOR
            ),
        }
    )
    axis_units = {
        HORMUZ_CALLS_LABEL: "艘次",
        HORMUZ_CAPACITY_LABEL: "百万吨",
        HORMUZ_TANKER_CAPACITY_LABEL: "百万吨",
    }
    if units is not None:
        axis_units.update(units)

    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups={
            HORMUZ_CALLS_LABEL: "left",
            HORMUZ_CAPACITY_LABEL: "right",
            HORMUZ_TANKER_CAPACITY_LABEL: "right",
        },
        title=HORMUZ_CHANNEL_TITLE,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    axis.set_ylim(bottom=0)
    # 容量从 0 起（模板 bar_series 只自动处理本轴，右轴线轴需手动语义起点）。
    axis.right_ax.set_ylim(bottom=0)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


def build_port_linkage_figure(
    values: pd.DataFrame,
    *,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """图2：UAE 港口总到港（左轴）与霍尔木兹油轮容量（右轴）联动图。"""

    display = _windowed(values, last_month)
    if display[UAE_PORT_CALLS].dropna().empty:
        raise ValueError(f"{PORT_LINKAGE_TITLE}没有可绘制的到港次数")
    frame = pd.DataFrame(
        {
            UAE_CALLS_LABEL: display[UAE_PORT_CALLS],
            HORMUZ_TANKER_CAPACITY_LABEL: (
                display[HORMUZ_TANKER_CAPACITY] / MT_FACTOR
            ),
        }
    )
    axis_units = {
        UAE_CALLS_LABEL: "艘次",
        HORMUZ_TANKER_CAPACITY_LABEL: "百万吨",
    }
    if units is not None:
        axis_units.update(units)

    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups={
            UAE_CALLS_LABEL: "left",
            HORMUZ_TANKER_CAPACITY_LABEL: "right",
        },
        title=PORT_LINKAGE_TITLE,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    axis.set_ylim(bottom=0)
    # 容量从 0 起（模板 bar_series 只自动处理本轴，右轴线轴需手动语义起点）。
    axis.right_ax.set_ylim(bottom=0)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "HORMUZ_CHANNEL_TITLE",
    "PORT_LINKAGE_TITLE",
    "build_hormuz_channel_figure",
    "build_port_linkage_figure",
]
