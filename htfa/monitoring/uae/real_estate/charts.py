"""DLD 迪拜房地产月度销售图：分交易类型与用途的笔数/金额双轴图。

每个口径一张图，直接使用 Ts ``plot_series`` 默认绘图模板（模板配色、
``style_axes`` 网格与脊线、月历刻度、战争基准线、底部图例与图注托管），
笔数柱在左轴、金额折线在右轴；窗口锚定最新完整月往前 36 个月。
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.periods import within_month_window
from htfa.monitoring.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from htfa.monitoring.uae.real_estate.data import (
    OFFPLAN_COMMERCIAL_AMOUNT,
    OFFPLAN_COMMERCIAL_COUNT,
    OFFPLAN_RESIDENTIAL_AMOUNT,
    OFFPLAN_RESIDENTIAL_COUNT,
    READY_COMMERCIAL_AMOUNT,
    READY_COMMERCIAL_COUNT,
    READY_RESIDENTIAL_AMOUNT,
    READY_RESIDENTIAL_COUNT,
)
from Ts.TsPlots.style import GRAY

COUNT_LABEL = "销售笔数"
AMOUNT_LABEL = "销售金额"

# 工作簿金额单位为百万 AED；图表统一折算为亿 AED（÷100）。
AMOUNT_UNIT_FACTOR = 100

DEFAULT_TITLES = {
    "期房住宅": "迪拜住宅期房",
    "期房商业": "迪拜商业地产期房",
    "现房住宅": "迪拜住宅现房",
    "现房商业": "迪拜商业地产现房",
}

PROPERTY_CONFIG = {
    "期房住宅": (OFFPLAN_RESIDENTIAL_COUNT, OFFPLAN_RESIDENTIAL_AMOUNT),
    "期房商业": (OFFPLAN_COMMERCIAL_COUNT, OFFPLAN_COMMERCIAL_AMOUNT),
    "现房住宅": (READY_RESIDENTIAL_COUNT, READY_RESIDENTIAL_AMOUNT),
    "现房商业": (READY_COMMERCIAL_COUNT, READY_COMMERCIAL_AMOUNT),
}

def sales_display_values(
    values: pd.DataFrame,
    *,
    last_month: pd.Period,
    market: str,
) -> pd.DataFrame:
    """返回分市场绘图值及原始百万 AED 金额，图表和下载使用同一口径。"""
    if market not in PROPERTY_CONFIG:
        raise ValueError(f"未知房地产口径：{market}")
    count_column, amount_column = PROPERTY_CONFIG[market]
    display = within_month_window(
        values[[count_column, amount_column]],
        first_month=last_month - 36, last_month=last_month,
    ).dropna(how="all").rename(columns={count_column: COUNT_LABEL, amount_column: AMOUNT_LABEL})
    display[f"{AMOUNT_LABEL}（百万AED）"] = display[AMOUNT_LABEL]
    display[AMOUNT_LABEL] = display[AMOUNT_LABEL] / AMOUNT_UNIT_FACTOR
    return display



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
    axis_units = {
        COUNT_LABEL: "笔",
        AMOUNT_LABEL: "亿迪拉姆",
    }
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
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    count_axis = normalize_ts_axis(returned_axis)
    count_axis.set_ylim(bottom=0)
    # 金额轴从 0 起（模板 bar_series 只自动处理柱所在轴，右轴线轴需手动语义起点）。
    count_axis.right_ax.set_ylim(bottom=0)
    annotate_war(count_axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "AMOUNT_LABEL",
    "AMOUNT_UNIT_FACTOR",
    "COUNT_LABEL",
    "DEFAULT_TITLES",
    "PROPERTY_CONFIG",
    "build_sales_figure",
    "sales_display_values",
]
