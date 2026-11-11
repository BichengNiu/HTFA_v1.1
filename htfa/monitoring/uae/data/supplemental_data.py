from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
import pandas as pd
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.supplemental_data import ChartSpec


def read_chart_data(
    content: PublishedUAEData, spec: ChartSpec, *, today: pd.Timestamp | None = None
):
    """校验频率与单位，返回原始序列及元数据供处理层聚合。"""
    with open_published_tables(content) as book:
        values, metadata = parse_target_sheet(
            book,
            sheet_name=spec.sheet,
            targets=tuple(((label, indicator) for label, indicator, _ in spec.series)),
            allowed_frequencies={spec.frequency},
            expected_unit={label: unit for label, _, unit in spec.series},
            zero_is_missing=spec.sheet == "日度_Wind",
        )
    return (metadata, values)
