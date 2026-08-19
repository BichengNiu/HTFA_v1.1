"""Monthly foreign-labour outflow indicators used beside the banking chart."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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
from dashboard.analysis.uae.sheet_reader import (
    SheetSeriesMetadata,
    format_updated_at,
    open_uae_workbook,
    optional_text,
)
from dashboard.preview.core.workbook_parser import normalize_indicator_name


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
    source_name: str


def load_foreign_labor_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> ForeignLaborData:
    """Read the two official labour-flow series from the foreign-labour sheet."""

    with open_uae_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        values, metadata = _parse_foreign_labor_sheet(excel_file)

    return ForeignLaborData(
        values=values,
        metadata=metadata,
        source_name=source_name,
    )


def _parse_foreign_labor_sheet(
    excel_file: pd.ExcelFile,
) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
    """Parse this sheet's documented date-first metadata layout strictly."""

    if FOREIGN_LABOR_SHEET not in excel_file.sheet_names:
        raise ValueError(f"工作簿缺少“{FOREIGN_LABOR_SHEET}”sheet")

    raw = pd.read_excel(excel_file, sheet_name=FOREIGN_LABOR_SHEET, header=None)
    if raw.shape[0] < 7 or raw.shape[1] < 3:
        raise ValueError(f"sheet“{FOREIGN_LABOR_SHEET}”不符合前六行元数据协议")
    expected_labels = {1: "日期", 2: "月", 3: "日期"}
    for row_index, expected in expected_labels.items():
        actual = optional_text(raw.iloc[row_index, 0])
        if actual != expected:
            raise ValueError(
                f"sheet“{FOREIGN_LABOR_SHEET}”第{row_index + 1}行首列应为“{expected}”，"
                f"实际为“{actual or '空'}”"
            )

    target_names = {NEPAL_APPROVALS, BANGLADESH_CLEARANCES}
    candidate_columns: dict[str, list[int]] = {}
    for column_index in range(1, raw.shape[1]):
        indicator_name = normalize_indicator_name(raw.iloc[1, column_index])
        if indicator_name in target_names:
            candidate_columns.setdefault(indicator_name, []).append(column_index)

    matching_columns: dict[str, int] = {}
    for indicator_name in target_names:
        columns = candidate_columns.get(indicator_name, [])
        compatible = [
            column_index
            for column_index in columns
            if optional_text(raw.iloc[2, column_index]) in {"月", "月度"}
            and optional_text(raw.iloc[3, column_index]) == "人"
            and optional_text(raw.iloc[4, column_index])
        ]
        if len(compatible) != 1:
            if not columns:
                raise ValueError(f"sheet“{FOREIGN_LABOR_SHEET}”缺少指标：{indicator_name}")
            raise ValueError(
                f"指标“{indicator_name}”应有唯一一列月度、人、且来源非空的观测"
            )
        matching_columns[indicator_name] = compatible[0]

    data_block = raw.iloc[6:, :].dropna(how="all")
    dates = pd.to_datetime(data_block.iloc[:, 0], errors="coerce")
    if dates.isna().any():
        row_number = int(dates[dates.isna()].index[0]) + 1
        raise ValueError(f"sheet“{FOREIGN_LABOR_SHEET}”第{row_number}行日期无效")
    if dates.duplicated().any():
        raise ValueError(f"sheet“{FOREIGN_LABOR_SHEET}”包含重复日期")

    series_map: dict[str, pd.Series] = {}
    metadata: dict[str, SheetSeriesMetadata] = {}
    for indicator_name, column_index in matching_columns.items():
        raw_values = data_block.iloc[:, column_index]
        numeric = pd.to_numeric(raw_values, errors="coerce")
        invalid = (
            raw_values.notna()
            & raw_values.astype(str).str.strip().ne("")
            & numeric.isna()
        )
        if invalid.any():
            row_number = int(invalid[invalid].index[0]) + 1
            raise ValueError(
                f"sheet“{FOREIGN_LABOR_SHEET}”指标“{indicator_name}”"
                f"第{row_number}行不是数值"
            )
        series = pd.Series(
            numeric.mask(numeric.eq(0)).to_numpy(),
            index=pd.DatetimeIndex(dates),
            name=indicator_name,
        ).dropna().sort_index()
        if series.empty:
            raise ValueError(f"指标“{indicator_name}”没有非零有效观测")
        series_map[indicator_name] = series
        metadata[indicator_name] = SheetSeriesMetadata(
            display_name=indicator_name,
            indicator_name=indicator_name,
            frequency=optional_text(raw.iloc[2, column_index]),
            unit=optional_text(raw.iloc[3, column_index]),
            source=optional_text(raw.iloc[4, column_index]),
            updated_at=format_updated_at(raw.iloc[5, column_index]),
            sheet_name=FOREIGN_LABOR_SHEET,
        )

    return (
        pd.concat(
            [series_map[NEPAL_APPROVALS], series_map[BANGLADESH_CLEARANCES]],
            axis=1,
            sort=False,
        ).sort_index(),
        metadata,
    )


def latest_common_month(values: pd.DataFrame) -> pd.Period:
    """Return the newest month where both plotted series are available."""

    return common_observations(values).index[-1].to_period("M")


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


def _recent_common_observations(values: pd.DataFrame) -> pd.DataFrame:
    """Match the oil charts' trailing three-year display window."""

    shared = common_observations(values)
    last_month = pd.Timestamp(shared.index[-1]).to_period("M")
    return within_month_window(
        shared,
        first_month=last_month - (DISPLAY_MONTHS - 1),
        last_month=last_month,
    )


def build_foreign_labor_figure(
    values: pd.DataFrame,
    *,
    title: str,
    source_text: str,
    units: Mapping[str, str | None] | None = None,
) -> Figure:
    """用 Ts 默认模板绘制尼泊尔与孟加拉国月度劳工人数（双柱、分居左右轴）。"""

    display_values = _recent_common_observations(values)
    frame = pd.DataFrame(
        {
            NEPAL_LABEL: display_values[NEPAL_APPROVALS],
            BANGLADESH_LABEL: display_values[BANGLADESH_CLEARANCES],
        }
    )
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
        figsize=(9.4, 6.2),
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
    "latest_common_month",
    "load_foreign_labor_data",
]
