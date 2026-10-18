"""从 DuckDB 发布快照读取 DLD 迪拜房地产月度销售数据。

``月度_DLD`` 沿用页面前六行元数据协议，但 8 个销售列单位混合
（笔数“笔”、金额“百万AED”），由共享目标读取器逐列校验单位，
并把住宅、商业两个分市场合并为「期房/现房 × 笔数/金额」四个聚合口径，
与用户「期房、现房笔数和金额」的展示口径一一对应。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from htfa.monitoring.uae.database import (
    PublishedUAEData,
    require_published_source,
)
from htfa.data.economic_workbook.shared.target_reader import parse_target_sheet

from htfa.data.economic_workbook import (
    SheetSeriesMetadata,
)
from htfa.monitoring.uae.periods import (
    anchor_last_month as _anchor_last_month,
    latest_complete_month as _latest_complete_month,
)


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

@dataclass(frozen=True)
class RealEstateData:
    """迪拜房地产月度销售数据及期房/现房合计口径。"""

    values: pd.DataFrame
    metadata: dict[str, SheetSeriesMetadata]
    raw_values: pd.DataFrame | None = None
    raw_metadata: dict[str, SheetSeriesMetadata] | None = None


def load_real_estate_data(
    source: PublishedUAEData,
) -> RealEstateData:
    """只读取 ``月度_DLD`` 的 8 个销售列并合并为 4 个聚合口径。"""

    source = require_published_source(source)
    with source.open() as tables:
        raw_values, raw_metadata = parse_target_sheet(
            tables, sheet_name=DLD_SHEET,
            targets=tuple((label, indicator) for label, indicator, _ in SALES_COLUMNS),
            allowed_frequencies={"月"},
            expected_unit={label: unit for label, _, unit in SALES_COLUMNS},
            strict_duplicates=True,
        )
        values, metadata = _aggregate_sales(raw_values, raw_metadata)

    return RealEstateData(
        values=values,
        metadata=metadata,
        raw_values=raw_values,
        raw_metadata=raw_metadata,
    )


def _aggregate_sales(
    raw_frame: pd.DataFrame,
    raw_metadata: dict[str, SheetSeriesMetadata],
) -> tuple[pd.DataFrame, dict[str, SheetSeriesMetadata]]:
    """把 8 个分市场序列合并为 4 个「期房/现房 × 笔数/金额」聚合列。"""

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
