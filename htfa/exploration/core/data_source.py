"""平稳性检验的数据源解析与频率表选择支持。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from htfa.data.file_content import file_fingerprint, read_file_bytes
from htfa.data.tabular import TabularInputSource

FREQUENCY_LABELS = {
    "daily": "日度数据",
    "weekly": "周度数据",
    "ten_day": "旬度数据",
    "monthly": "月度数据",
    "quarterly": "季度数据",
    "yearly": "年度数据",
}
_TABULAR_INPUT_SOURCE = TabularInputSource()


@dataclass(frozen=True)
class ExploreDataset:
    """一次解析后供整个数据探索模块共享的数据集。"""

    fingerprint: str
    file_name: str
    tables: dict[str, pd.DataFrame]


def load_explore_dataset(file_input: Any) -> ExploreDataset:
    """按统一契约解析数据探索模块使用的数据集。"""
    file_name = Path(str(getattr(file_input, "name", file_input))).name
    tables = _TABULAR_INPUT_SOURCE.read(file_input, file_name)
    return ExploreDataset(
        fingerprint=file_fingerprint(read_file_bytes(file_input)),
        file_name=file_name,
        tables=tables,
    )


def format_table_option(table_key: str, tables: dict[str, pd.DataFrame]) -> str:
    """生成包含频率、行数和指标数的数据表选项文本。"""
    frame = tables[table_key]
    label = FREQUENCY_LABELS.get(table_key, "数据表")
    return f"{label}（{len(frame)} 行 × {len(frame.columns)} 个指标）"


__all__ = [
    "FREQUENCY_LABELS",
    "ExploreDataset",
    "format_table_option",
    "load_explore_dataset",
]
