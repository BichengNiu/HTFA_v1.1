from __future__ import annotations
from htfa.monitoring.uae.data.database import open_published_tables
from htfa.monitoring.uae.contracts.publication import PublishedUAEData
from htfa.monitoring.uae.data.database import require_published_source
from htfa.data.economic_workbook.target_reader import parse_target_sheet
from htfa.monitoring.uae.contracts.government_finance.search_index import SEARCH_SHEET
from htfa.monitoring.uae.contracts.government_finance.search_index import (
    SEARCH_INDICATORS,
)


def read_search_index_data(source: PublishedUAEData):
    """从 DuckDB 的 ``月度_工作搜索热度`` 读取谷歌趋势序列。"""
    with open_published_tables(source) as tables:
        values, _ = parse_target_sheet(
            tables,
            sheet_name=SEARCH_SHEET,
            targets=SEARCH_INDICATORS,
            allowed_frequencies={"月", "月度"},
            expected_unit="指数",
            zero_is_missing=False,
        )
    return (values,)
