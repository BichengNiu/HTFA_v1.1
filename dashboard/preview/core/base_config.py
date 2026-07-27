"""数据预览频率配置模型。"""

from typing import List
from dataclasses import dataclass


@dataclass
class FrequencyConfig:
    """频率配置数据类"""
    english_name: str
    display_name: str
    sort_column: str
    highlight_columns: List[str]
    percentage_columns: List[str]
    indicator_name_column: str
    date_column: str
    column_order: List[str]
    color: str = "#1f77b4"
