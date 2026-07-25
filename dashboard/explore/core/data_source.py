"""平稳性检验的数据源解析与频率表选择支持。"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from dashboard.preview.modules.uae.config import UAEConfig
from dashboard.preview.modules.uae.loader import UAELoader


FREQUENCY_LABELS = {
    "daily": "日度数据",
    "weekly": "周度数据",
    "ten_day": "旬度数据",
    "monthly": "月度数据",
    "quarterly": "季度数据",
    "yearly": "年度数据",
}


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


def load_stationarity_tables(file_input: Any) -> dict[str, pd.DataFrame]:
    """解析上传文件，返回可供平稳性检验选择的非空数据表。"""
    file_name = Path(str(getattr(file_input, "name", file_input))).name
    suffix = Path(file_name).suffix.lower()

    if suffix == ".csv":
        data = pd.read_csv(BytesIO(read_uploaded_bytes(file_input)))
        if data.empty:
            raise ValueError("CSV 文件中没有可分析数据")
        return {"table": data}

    if suffix not in {".xlsx", ".xls"}:
        raise ValueError("仅支持 CSV、XLSX 和 XLS 文件")

    loaded = UAELoader(UAEConfig()).load_and_process_data([file_input])
    tables = {
        frequency: frame
        for frequency, frame in loaded.get_all_dataframes().items()
        if frame is not None and not frame.empty
    }
    if not tables:
        raise ValueError("工作簿解析成功，但没有发现非空的频率数据表")
    return tables


def format_table_option(table_key: str, tables: dict[str, pd.DataFrame]) -> str:
    """生成包含频率、行数和指标数的数据表选项文本。"""
    frame = tables[table_key]
    label = FREQUENCY_LABELS.get(table_key, "数据表")
    return f"{label}（{len(frame)} 行 × {len(frame.columns)} 个指标）"


__all__ = [
    "FREQUENCY_LABELS",
    "fingerprint_uploaded_file",
    "format_table_option",
    "load_stationarity_tables",
    "read_uploaded_bytes",
]
