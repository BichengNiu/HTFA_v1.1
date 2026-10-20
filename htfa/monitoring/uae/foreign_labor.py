"""Monthly foreign-labour outflow indicators used beside the banking chart."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd
from matplotlib.figure import Figure
from Ts.TsPlots import plot_series

from htfa.monitoring.uae.database import PublishedUAEData, require_published_source
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.monitoring.uae.periods import within_month_window
from htfa.monitoring.uae.plot_helpers import (
    create_report_axis,
    WAR_START_DATE,
    annotate_war,
    apply_htfa_fonts,
    normalize_ts_axis,
    source_note,
)
from htfa.data.economic_workbook import SheetSeriesMetadata


FOREIGN_LABOR_SHEET = "月度_外籍劳动力"
NEPAL_APPROVALS = "尼泊尔_DoFE批准_含再入境"
BANGLADESH_CLEARANCES = "孟加拉国_BMET出境许可"

# 作图用裸变量名（模板双轴时会自动追加（左轴/右轴）后缀）。
NEPAL_LABEL = "尼泊尔劳工人数"
BANGLADESH_LABEL = "孟加拉国劳工人数"

SERIES_SPECS = (
    (NEPAL_APPROVALS, NEPAL_LABEL),
    (BANGLADESH_CLEARANCES, BANGLADESH_LABEL),
)

DISPLAY_MONTHS = 37


@dataclass(frozen=True)
class ForeignLaborData:
    """The two monthly labour-flow series displayed in the companion chart."""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]


def load_foreign_labor_data(
    source: PublishedUAEData,
) -> ForeignLaborData:
    """Read the two official labour-flow series from the foreign-labour sheet."""

    source = require_published_source(source)
    with source.open() as tables:
        values, metadata = parse_target_sheet(
            tables,
            sheet_name=FOREIGN_LABOR_SHEET,
            targets=tuple((name, name) for name, _ in SERIES_SPECS),
            allowed_frequencies={"月"},
            expected_unit="人",
        )

    return ForeignLaborData(
        values=values,
        metadata=metadata,
    )


def common_observations(values: pd.DataFrame) -> pd.DataFrame:
    """Keep only months with observations for both countries, from their common start."""

    required_columns = [column for column, *_ in SERIES_SPECS]
    missing_columns = [column for column in required_columns if column not in values]
    if missing_columns:
        raise KeyError(f"缺少外籍劳动力图表指标：{missing_columns}")
    shared = values[required_columns].dropna(how="any").sort_index()
    if shared.empty:
        raise ValueError("尼泊尔与孟加拉国没有共同的有效月度观测")
    return shared


def display_foreign_labor_values(values: pd.DataFrame) -> pd.DataFrame:
    """Match the oil charts' trailing three-year display window."""

    shared = common_observations(values)
    last_month = pd.Timestamp(shared.index[-1]).to_period("M")
    return within_month_window(
        shared,
        first_month=last_month - (DISPLAY_MONTHS - 1),
        last_month=last_month,
    ).rename(columns=dict(SERIES_SPECS))


def build_foreign_labor_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """用 Ts 默认模板绘制尼泊尔与孟加拉国月度劳工人数（双柱、分居左右轴）。"""

    frame = display_foreign_labor_values(values)
    axis_units = {NEPAL_LABEL: "人", BANGLADESH_LABEL: "人"}
    if units is not None:
        axis_units.update(units)

    figure, returned_axis = plot_series(
        frame,
        facet=False,
        axis_groups={NEPAL_LABEL: "left", BANGLADESH_LABEL: "right"},
        title=title,
        xtitle="",
        ytitle_position="side",
        year_ruler=True,
        grid=True,
        bar_series=[NEPAL_LABEL, BANGLADESH_LABEL],
        vlines=WAR_START_DATE,
        show_legend=True,
        note=source_note(source_text),
        note_loc="left",
        ax=create_report_axis(),
        units=axis_units,
    )
    axis = normalize_ts_axis(returned_axis)
    annotate_war(axis)
    apply_htfa_fonts(figure)
    return figure


__all__ = [
    "BANGLADESH_CLEARANCES",
    "BANGLADESH_LABEL",
    "FOREIGN_LABOR_SHEET",
    "ForeignLaborData",
    "NEPAL_APPROVALS",
    "NEPAL_LABEL",
    "SERIES_SPECS",
    "build_foreign_labor_figure",
    "common_observations",
    "display_foreign_labor_values",
    "load_foreign_labor_data",
]
