"""从阿联酋工作簿读取月度_LSEG 的阿联酋非油私营部门 PMI。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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
from htfa.data.economic_workbook import (
    EconomicWorkbookReader,
    SheetSeriesMetadata,
)


PMI_SHEET = "月度_LSEG"
PMI_LABEL = "阿联酋非油私营部门采购经理人指数(PMI)"
PMI_INDICATOR = PMI_LABEL
PMI_DISPLAY_NAME = "非油私营部门采购经理指数（PMI）"

DISPLAY_MONTHS = 37
_WORKBOOK_READER = EconomicWorkbookReader(
    "uae_monitoring",
    "monitoring.uae",
)


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

    with _WORKBOOK_READER.open_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        values, metadata = _WORKBOOK_READER.read_target_sheet(
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
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """绘制阿联酋非油私营部门 PMI 的月度线图。"""

    display_values = display_pmi_values(values)
    if display_values.dropna(how="all").empty:
        raise ValueError(f"{title}没有可绘制的有效数据")

    axis_units = {PMI_LABEL: "点"}
    if units is not None:
        axis_units.update(units)
    figure, returned_axis = plot_series(
        display_values[PMI_LABEL].rename(PMI_LABEL),
        facet=False,
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        vlines=WAR_START_DATE,
        show_legend=True,
        legend_labels=[PMI_DISPLAY_NAME],
        note=source_note(source_text),
        note_loc="left",
        figsize=(9.4, 6.2),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "PMI_INDICATOR",
    "PMI_LABEL",
    "PMI_DISPLAY_NAME",
    "PMI_SHEET",
    "PmiData",
    "build_pmi_figure",
    "display_pmi_values",
    "load_pmi_data",
]
