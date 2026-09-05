"""数据预览频率配置模型。"""

from dataclasses import dataclass


@dataclass
class FrequencyConfig:
    """频率配置数据类"""
    english_name: str
    display_name: str
    sort_column: str
    highlight_columns: list[str]
    percentage_columns: list[str]
    indicator_name_column: str
    date_column: str
    column_order: list[str]
    color: str = "#1f77b4"

    @property
    def df_key(self) -> str:
        return f"{self.english_name}_df"

    @property
    def industries_key(self) -> str:
        return f"{self.english_name}_industries"

    @property
    def empty_message(self) -> str:
        return f"暂无{self.display_name}数据。"

    @property
    def download_prefix(self) -> str:
        return f"{self.display_name}数据摘要"
