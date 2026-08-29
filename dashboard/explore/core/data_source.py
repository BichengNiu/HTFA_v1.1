"""平稳性检验的数据源解析与频率表选择支持。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from dashboard.preview.core.workbook_parser import parse_preview_workbook

FREQUENCY_LABELS = {
    "daily": "日度数据",
    "weekly": "周度数据",
    "ten_day": "旬度数据",
    "monthly": "月度数据",
    "quarterly": "季度数据",
    "yearly": "年度数据",
}


@dataclass(frozen=True)
class ExploreDataset:
    """一次解析后供整个数据探索模块共享的数据集。"""

    fingerprint: str
    file_name: str
    tables: dict[str, pd.DataFrame]
    metadata_map: dict[str, Any]


def read_uploaded_bytes(file_input: Any) -> bytes:
    """读取上传文件内容，同时避免依赖文件对象的当前游标位置。"""
    if hasattr(file_input, "getvalue"):
        return file_input.getvalue()
    if hasattr(file_input, "read"):
        content = file_input.read()
        if hasattr(file_input, "seek"):
            file_input.seek(0)
        return content
    if isinstance(file_input, (str, Path)):
        return Path(file_input).read_bytes()
    raise TypeError("数据文件必须是路径或可读取的二进制文件对象")


def fingerprint_uploaded_file(file_input: Any) -> str:
    """返回用于识别同名文件内容变化的 SHA-256 指纹。"""
    return sha256(read_uploaded_bytes(file_input)).hexdigest()


def load_stationarity_data(
    file_input: Any,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """解析上传文件，返回可分析数据表及每个指标的工作簿元数据。"""
    file_name = Path(str(getattr(file_input, "name", file_input))).name
    suffix = Path(file_name).suffix.lower()

    if suffix == ".csv":
        data = pd.read_csv(BytesIO(read_uploaded_bytes(file_input)))
        if data.empty:
            raise ValueError("CSV 文件中没有可分析数据")
        return {"table": data}, {}

    if suffix not in {".xlsx", ".xls"}:
        raise ValueError("仅支持 CSV、XLSX 和 XLS 文件")

    loaded = parse_preview_workbook(file_input, module_name="uae")
    tables = {
        frequency: frame
        for frequency, frame in loaded.get_all_dataframes().items()
        if frame is not None and not frame.empty
    }
    if not tables:
        raise ValueError("工作簿解析成功，但没有发现非空的频率数据表")
    return tables, dict(loaded.indicator_metadata_map)


def load_explore_dataset(file_input: Any) -> ExploreDataset:
    """按统一契约解析数据探索模块使用的数据集。"""
    file_name = Path(str(getattr(file_input, "name", file_input))).name
    tables, metadata_map = load_stationarity_data(file_input)
    return ExploreDataset(
        fingerprint=fingerprint_uploaded_file(file_input),
        file_name=file_name,
        tables=tables,
        metadata_map=metadata_map,
    )


def format_table_option(table_key: str, tables: dict[str, pd.DataFrame]) -> str:
    """生成包含频率、行数和指标数的数据表选项文本。"""
    frame = tables[table_key]
    label = FREQUENCY_LABELS.get(table_key, "数据表")
    return f"{label}（{len(frame)} 行 × {len(frame.columns)} 个指标）"


__all__ = [
    "FREQUENCY_LABELS",
    "ExploreDataset",
    "fingerprint_uploaded_file",
    "format_table_option",
    "load_explore_dataset",
    "load_stationarity_data",
    "read_uploaded_bytes",
]
