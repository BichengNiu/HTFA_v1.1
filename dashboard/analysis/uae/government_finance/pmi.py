"""从阿联酋工作簿读取月度_LSEG 的阿联酋非油私营部门 PMI。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from dashboard.analysis.uae.oil.alignment import within_month_window
from dashboard.analysis.uae.plot_helpers import (
    add_source_note,
    annotate_war,
    apply_strict_month_ticks,
    finish_dual_axis_figure,
    new_ts_figure_axis,
    normalize_ts_axis,
)
from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    open_uae_workbook,
    parse_target_sheet,
)


PMI_SHEET = "月度_LSEG"
PMI_LABEL = "阿联酋非油私营部门采购经理人指数(PMI)"
PMI_INDICATOR = PMI_LABEL
PMI_COLOR = "#000000"

DISPLAY_MONTHS = 37


@dataclass(frozen=True)
class PmiData:
    """阿联酋非油私营部门月度 PMI 序列及来源信息。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str


def load_pmi_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> PmiData:
    """只读取 ``月度_LSEG`` 的单一 PMI 指标并校验元数据。"""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        values, metadata = parse_target_sheet(
            excel_file,
            sheet_name=PMI_SHEET,
            targets=((PMI_LABEL, PMI_INDICATOR),),
            allowed_frequencies={"月", "月度"},
            expected_unit="点",
        )

    return PmiData(
        values=values,
        metadata=metadata,
        source_name=source_name,
    )


def display_pmi_values(values: pd.DataFrame) -> pd.DataFrame:
    """返回最近展示窗口内的 PMI 序列。"""

    last_month = pd.Timestamp(values.index[-1]).to_period("M")
    return within_month_window(
        values,
        first_month=last_month - (DISPLAY_MONTHS - 1),
        last_month=last_month,
    )


def build_pmi_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
) -> Figure:
    """绘制阿联酋非油私营部门 PMI 的月度线图。"""

    display_values = display_pmi_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    figure, axis = new_ts_figure_axis()
    figure, returned_axis = plot_series(
        display_values[PMI_LABEL].rename(PMI_LABEL),
        title=None,
        xtitle="",
        ytitle="点",
        ytitle_position="side",
        colors=[PMI_COLOR],
        linewidth=2.2,
        markersize=0,
        max_ticks=8,
        show_legend=False,
        note=None,
        grid=True,
        ax=axis,
    )
    axis = normalize_ts_axis(returned_axis)

    axis.set_title(title, fontsize=14, pad=14)
    axis.set_ylabel("点", fontsize=12)
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color("#6B7280")
        spine.set_linewidth(0.9)
    apply_strict_month_ticks(axis, display_values.index)
    annotate_war(axis)
    finish_dual_axis_figure(figure, top=0.90)
    add_source_note(figure, source_text)
    return figure


__all__ = [
    "PMI_COLOR",
    "PMI_INDICATOR",
    "PMI_LABEL",
    "PMI_SHEET",
    "PmiData",
    "build_pmi_figure",
    "display_pmi_values",
    "load_pmi_data",
]