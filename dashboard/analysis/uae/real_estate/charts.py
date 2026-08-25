"""DLD 迪拜房地产月度销售图：期房 / 现房 笔数柱 + 金额线双轴图。

每市场一张图，直接使用 Ts ``plot_series`` 默认绘图模板（模板配色、
``style_axes`` 网格与脊线、月历刻度、战争基准线、底部图例与图注托管），
笔数柱在左轴、金额折线在右轴；窗口锚定最新完整月往前 36 个月。
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.periods import within_month_window
from dashboard.analysis.uae.plot_helpers import (
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from dashboard.analysis.uae.real_estate.data import (
    OFFPLAN_AMOUNT,
    OFFPLAN_COUNT,
    READY_AMOUNT,
    READY_COUNT,
)
from Ts.TsPlots.style import GRAY

COUNT_LABEL = "销售笔数"
AMOUNT_LABEL = "销售金额"

# 工作簿金额单位为百万 AED；图表统一折算为亿 AED（÷100）。
AMOUNT_UNIT_FACTOR = 100

DEFAULT_TITLES = {
    "期房": "迪拜期房销售：笔数与金额",
    "现房": "迪拜现房销售：笔数与金额",
}

MARKET_CONFIG = {
    "期房": (OFFPLAN_COUNT, OFFPLAN_AMOUNT),
    "现房": (READY_COUNT, READY_AMOUNT),
}


def sales_display_values(
    values: pd.DataFrame,
    *,
    last_month: pd.Period,
) -> pd.DataFrame:
    """返回窗口内的展示表：笔数不变、金额由百万 AED 折算为亿 AED。"""

    display_values = within_month_window(
        values,
        first_month=last_month - 36,
        last_month=last_month,
    ).dropna(how="all")
    converted = display_values.copy()
    for column in (OFFPLAN_AMOUNT, READY_AMOUNT):
        converted[column] = display_values[column] / AMOUNT_UNIT_FACTOR
    return converted


def build_sales_figure(
    values: pd.DataFrame,
    *,
    market: str,
    title: str,
    source_text: str,
    last_month: pd.Period,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制某市场（期房/现房）的笔数柱 + 金额线双轴图（Ts 默认模板）。

    ``values`` 为四个聚合口径的完整月度表；窗口在函数内按
    ``[last_month-36, last_month]`` 截取，与板块锚定月保持一致。
    """

    if market not in MARKET_CONFIG:
        raise ValueError(f"未知房地产市场：{market}")
    count_col, amount_col = MARKET_CONFIG[market]

    display_values = sales_display_values(values, last_month=last_month)
    if display_values[count_col].dropna().empty:
        raise ValueError(f"{title}没有可绘制的有效笔数")
    if display_values[amount_col].dropna().empty:
        raise ValueError(f"{title}没有可绘制的有效金额")

    frame = pd.DataFrame(
        {
            COUNT_LABEL: display_values[count_col],
            AMOUNT_LABEL: display_values[amount_col],
        }
    )
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
    "MARKET_CONFIG",
    "build_sales_figure",
    "sales_display_values",
]
