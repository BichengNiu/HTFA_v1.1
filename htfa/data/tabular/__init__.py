"""普通表格数据能力：文件读取、解析与数据集契约。"""

from .dataset import (
    OverviewDataset,
    build_overview_dataset,
    numeric_variable_names,
    suggest_time_column,
)
from .file_parsing import (
    FileParseError,
    build_dataframe_from_rows,
    list_excel_sheets,
    load_dataframe,
    read_raw_rows,
)

__all__ = [
    "FileParseError",
    "OverviewDataset",
    "build_dataframe_from_rows",
    "build_overview_dataset",
    "list_excel_sheets",
    "load_dataframe",
    "numeric_variable_names",
    "read_raw_rows",
    "suggest_time_column",
]
