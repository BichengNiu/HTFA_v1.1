"""从阿联酋工作簿读取 DLD 迪拜房地产月度销售数据。

``月度_DLD`` 沿用页面前六行元数据协议，但 8 个销售列单位混合
（笔数“笔”、金额“百万AED”），因此用定制解析（与 ``ded`` 一致），
并把住宅、商业两个分市场合并为「期房/现房 × 笔数/金额」四个聚合口径，
与用户「期房、现房笔数和金额」的展示口径一一对应。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from htfa.data.economic_workbook import (
    EconomicWorkbookReader,
    SheetSeriesMetadata,
    format_updated_at,
    optional_text,
)
from htfa.monitoring.uae.periods import (
    anchor_last_month as _anchor_last_month,
    latest_complete_month as _latest_complete_month,
)
from htfa.data.economic_workbook import normalize_indicator_name


DLD_SHEET = "月度_DLD"

OFFPLAN_COUNT = "期房销售笔数"
OFFPLAN_AMOUNT = "期房销售金额"
READY_COUNT = "现房销售笔数"
READY_AMOUNT = "现房销售金额"

OFFPLAN_RESIDENTIAL_COUNT = "期房住宅笔数"
OFFPLAN_RESIDENTIAL_AMOUNT = "期房住宅金额"
READY_RESIDENTIAL_COUNT = "现房住宅笔数"
READY_RESIDENTIAL_AMOUNT = "现房住宅金额"
OFFPLAN_COMMERCIAL_COUNT = "期房商业笔数"
OFFPLAN_COMMERCIAL_AMOUNT = "期房商业金额"
READY_COMMERCIAL_COUNT = "现房商业笔数"
READY_COMMERCIAL_AMOUNT = "现房商业金额"

# 月度_DLD 销售 8 列：4 分市场 ×（笔数/金额），(展示名, 原始指标名, 单位)。
SALES_COLUMNS: tuple[tuple[str, str, str], ...] = (
    (OFFPLAN_RESIDENTIAL_COUNT, "迪拜:期房销售-住宅笔数", "笔"),
    (
        OFFPLAN_RESIDENTIAL_AMOUNT,
        "迪拜:期房销售-住宅金额(百万AED)",
        "百万AED",
    ),
    (READY_RESIDENTIAL_COUNT, "迪拜:现房销售-住宅笔数", "笔"),
    (
        READY_RESIDENTIAL_AMOUNT,
        "迪拜:现房销售-住宅金额(百万AED)",
        "百万AED",
    ),
    (OFFPLAN_COMMERCIAL_COUNT, "迪拜:期房销售-商业笔数", "笔"),
    (
        OFFPLAN_COMMERCIAL_AMOUNT,
        "迪拜:期房销售-商业金额(百万AED)",
        "百万AED",
    ),
    (READY_COMMERCIAL_COUNT, "迪拜:现房销售-商业笔数", "笔"),
    (
        READY_COMMERCIAL_AMOUNT,
        "迪拜:现房销售-商业金额(百万AED)",
        "百万AED",
    ),
)

# 4 个聚合口径：住宅 + 商业 合计（min_count=1：仅当两个分市场当月都缺失才留空）。
AGGREGATE_TARGETS: tuple[tuple[str, tuple[str, str], str], ...] = (
    (
        OFFPLAN_COUNT,
        (OFFPLAN_RESIDENTIAL_COUNT, OFFPLAN_COMMERCIAL_COUNT),
        "笔",
    ),
    (
        OFFPLAN_AMOUNT,
        (OFFPLAN_RESIDENTIAL_AMOUNT, OFFPLAN_COMMERCIAL_AMOUNT),
        "百万AED",
    ),
    (READY_COUNT, (READY_RESIDENTIAL_COUNT, READY_COMMERCIAL_COUNT), "笔"),
    (
        READY_AMOUNT,
        (READY_RESIDENTIAL_AMOUNT, READY_COMMERCIAL_AMOUNT),
        "百万AED",
    ),
)
_WORKBOOK_READER = EconomicWorkbookReader(
    "uae_monitoring",
    "monitoring.uae",
)

@dataclass(frozen=True)
class RealEstateData:
    """迪拜房地产月度销售数据及期房/现房合计口径。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    source_name: str
    raw_values: pd.DataFrame | None = None
    raw_metadata: dict[str, SheetSeriesMetadata] | None = None


def load_real_estate_data(
    file_input: Any,
    *,
    file_name: str | None = None,
) -> RealEstateData:
    """只读取 ``月度_DLD`` 的 8 个销售列并合并为 4 个聚合口径。"""

    with _WORKBOOK_READER.open_workbook(file_input, file_name=file_name) as (
        excel_file,
        source_name,
    ):
        series_map, raw_metadata = _parse_sales_sheet(excel_file)
        raw_values = pd.concat(
            [series_map[name] for name, _, _ in SALES_COLUMNS],
            axis=1,
            sort=False,
        ).sort_index()
        values, metadata = _aggregate_sales(series_map, raw_metadata)

    return RealEstateData(
        values=values,
        metadata=metadata,
        source_name=source_name,
        raw_values=raw_values,
        raw_metadata=raw_metadata,
    )


def _parse_sales_sheet(
    excel_file: pd.ExcelFile,
) -> tuple[dict[str, pd.Series], dict[str, SheetSeriesMetadata]]:
    """按标准元数据布局解析 DLD 的八个销售指标。"""

    raw = _WORKBOOK_READER.read_raw_sheet(excel_file, sheet_name=DLD_SHEET)
    _WORKBOOK_READER.validate_target_sheet(raw, DLD_SHEET)

    normalized_targets = {
        normalize_indicator_name(indicator_name): display_name
        for display_name, indicator_name, _ in SALES_COLUMNS
    }
    candidate_columns: dict[str, list[int]] = {}
    for column_index in range(1, raw.shape[1]):
        normalized_name = normalize_indicator_name(raw.iloc[1, column_index])
        if normalized_name in normalized_targets:
            candidate_columns.setdefault(
                normalized_targets[normalized_name], []
            ).append(column_index)

    matching_columns: dict[str, int] = {}
    for display_name, indicator_name, unit in SALES_COLUMNS:
        columns = candidate_columns.get(display_name, [])
        if len(columns) != 1:
            if not columns:
                raise ValueError(f"sheet“{DLD_SHEET}”缺少指标：{indicator_name}")
            raise ValueError(f"sheet“{DLD_SHEET}”包含重复指标：{indicator_name}")
        column_index = columns[0]
        frequency = optional_text(raw.iloc[2, column_index])
        actual_unit = optional_text(raw.iloc[3, column_index])
        source = optional_text(raw.iloc[4, column_index])
        if frequency != "月" or actual_unit != unit or not source:
            raise ValueError(
                f"指标“{indicator_name}”的频率、单位或来源不符合当前工作簿契约"
            )
        matching_columns[display_name] = column_index

    data_block = raw.iloc[6:, :].dropna(how="all")
    dates = pd.to_datetime(data_block.iloc[:, 0], errors="coerce")
    if dates.isna().any():
        row_number = int(dates[dates.isna()].index[0]) + 1
        raise ValueError(f"sheet“{DLD_SHEET}”第{row_number}行日期无效")
    if dates.duplicated().any():
        raise ValueError(f"sheet“{DLD_SHEET}”包含重复日期")

    series_map: dict[str, pd.Series] = {}
    metadata: dict[str, SheetSeriesMetadata] = {}
    for display_name, column_index in matching_columns.items():
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
                f"sheet“{DLD_SHEET}”指标“{display_name}”"
                f"第{row_number}行不是数值"
            )
        series = pd.Series(
            numeric.mask(numeric.eq(0)).to_numpy(),
            index=pd.DatetimeIndex(dates),
            name=display_name,
        ).dropna().sort_index()
        if series.empty:
            raise ValueError(f"指标“{display_name}”没有非零有效观测")
        series_map[display_name] = series
        metadata[display_name] = SheetSeriesMetadata(
            display_name=display_name,
            indicator_name=normalize_indicator_name(raw.iloc[1, column_index]),
            frequency=optional_text(raw.iloc[2, column_index]),
            unit=optional_text(raw.iloc[3, column_index]),
            source=optional_text(raw.iloc[4, column_index]),
            updated_at=format_updated_at(raw.iloc[5, column_index]),
            sheet_name=DLD_SHEET,
        )
    return series_map, metadata


def _aggregate_sales(
    series_map: dict[str, pd.Series],
    raw_metadata: dict[str, SheetSeriesMetadata],
) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
    """把 8 个分市场序列合并为 4 个「期房/现房 × 笔数/金额」聚合列。"""

    raw_frame = pd.concat(
        [series_map[name] for name, _, _ in SALES_COLUMNS],
        axis=1,
        sort=False,
    ).sort_index()

    values = pd.DataFrame(index=raw_frame.index)
    metadata: dict[str, SheetSeriesMetadata] = {}
    for aggregate_name, parts, unit in AGGREGATE_TARGETS:
        example = raw_metadata[parts[0]]
        series = (
            raw_frame[list(parts)]
            .sum(axis=1, min_count=1)
            .rename(aggregate_name)
            .dropna()
        )
        values[aggregate_name] = series
        metadata[aggregate_name] = SheetSeriesMetadata(
            display_name=aggregate_name,
            indicator_name=" + ".join(
                raw_metadata[part].indicator_name for part in parts
            ),
            frequency=example.frequency,
            unit=unit,
            source=example.source,
            updated_at=example.updated_at,
            sheet_name=DLD_SHEET,
        )
    return values.sort_index(), metadata


def latest_complete_month(values: pd.DataFrame) -> pd.Timestamp:
    """返回期房/现房笔数与金额四个口径均有效的最新月份。"""

    return _latest_complete_month(
        values,
        empty_message="月度_DLD 没有四个销售口径均完整的月份",
    )


def anchor_last_month(
    values: pd.DataFrame,
    *,
    today: pd.Timestamp | None = None,
) -> pd.Period:
    """锚定**已结束**的最新月份（图表窗口右端）。

    工作簿的最新月若恰为当前自然月（该月尚未过完、数值是截至目前的滚动统计），
    则选择上一个完整月；否则直接取数据侧最新完整月。``today`` 仅测试注入。
    """

    return _anchor_last_month(
        values,
        today=today,
        empty_message="月度_DLD 没有四个销售口径均完整的月份",
    )


__all__ = [
    "AGGREGATE_TARGETS",
    "DLD_SHEET",
    "OFFPLAN_AMOUNT",
    "OFFPLAN_COMMERCIAL_AMOUNT",
    "OFFPLAN_COMMERCIAL_COUNT",
    "OFFPLAN_COUNT",
    "OFFPLAN_RESIDENTIAL_AMOUNT",
    "OFFPLAN_RESIDENTIAL_COUNT",
    "READY_COMMERCIAL_AMOUNT",
    "READY_COMMERCIAL_COUNT",
    "READY_AMOUNT",
    "READY_COUNT",
    "READY_RESIDENTIAL_AMOUNT",
    "READY_RESIDENTIAL_COUNT",
    "RealEstateData",
    "anchor_last_month",
    "latest_complete_month",
    "load_real_estate_data",
]
