from __future__ import annotations
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData

from htfa.preview.data.economic_workbook import SheetSeriesMetadata
from htfa.monitoring.uae.processing.periods import (
    anchor_last_month as _anchor_last_month,
)
from htfa.monitoring.uae.contracts.real_estate.data import DLD_SHEET
from htfa.monitoring.uae.contracts.real_estate.data import AGGREGATE_TARGETS
from htfa.monitoring.uae.contracts.real_estate.data import RealEstateData
from htfa.monitoring.uae.data.real_estate.data import read_real_estate_data


def load_real_estate_data(source: PublishedUAEData) -> RealEstateData:
    """只读取 ``月度_DLD`` 的 8 个销售列并合并为 4 个聚合口径。"""
    raw_metadata, raw_values = read_real_estate_data(source)
    values, metadata = _aggregate_sales(raw_values, raw_metadata)
    return RealEstateData(
        values=values,
        metadata=metadata,
        raw_values=raw_values,
        raw_metadata=raw_metadata,
    )


def _aggregate_sales(
    raw_frame: pd.DataFrame, raw_metadata: dict[str, SheetSeriesMetadata]
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
                (raw_metadata[part].indicator_name for part in parts)
            ),
            frequency=example.frequency,
            unit=unit,
            source=example.source,
            updated_at=example.updated_at,
            sheet_name=DLD_SHEET,
        )
    return (values.sort_index(), metadata)


def anchor_last_month(
    values: pd.DataFrame, *, today: pd.Timestamp | None = None
) -> pd.Period:
    """锚定**已结束**的最新月份（图表窗口右端）。

    工作簿的最新月若恰为当前自然月（该月尚未过完、数值是截至目前的滚动统计），
    则选择上一个完整月；否则直接取数据侧最新完整月。``today`` 仅测试注入。
    """
    return _anchor_last_month(
        values, today=today, empty_message="月度_DLD 没有四个销售口径均完整的月份"
    )
