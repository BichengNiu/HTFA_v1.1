"""
领域模型定义

定义数据预览相关的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd


@dataclass(frozen=True)
class IndicatorMetadata:
    """单个指标在字典、数据sheet和物理文件中的完整元数据。"""

    indicator_name: str
    frequency: str
    unit: str
    sheet_source: str
    updated_at: str
    indicator_type: Optional[str] = None
    industry: Optional[str] = None
    dictionary_source: Optional[str] = None
    forecast_variable: Optional[str] = None
    file_name: str = ""
    sheet_name: str = ""


@dataclass
class LoadedPreviewData:
    """预览数据加载结果的通用封装

    设计原则:
    - 不可变性: 使用dataclass确保数据一致性
    - 通用性: 支持任意频率和映射关系
    """

    # DataFrame数据 (使用字典存储，支持任意频率)
    dataframes: Dict[str, pd.DataFrame] = field(default_factory=dict)

    # 映射关系
    source_map: Dict[str, str] = field(default_factory=dict)
    indicator_industry_map: Dict[str, str] = field(default_factory=dict)
    indicator_unit_map: Dict[str, str] = field(default_factory=dict)
    indicator_type_map: Dict[str, str] = field(default_factory=dict)
    indicator_freq_map: Dict[str, str] = field(default_factory=dict)
    indicator_metadata_map: Dict[str, IndicatorMetadata] = field(default_factory=dict)

    # 元数据
    module_name: str = "unknown"

    def get_dataframe(self, frequency: str) -> pd.DataFrame:
        """获取指定频率的DataFrame

        Args:
            frequency: 频率名称 (如 'weekly', 'monthly')

        Returns:
            pd.DataFrame: 指定频率的DataFrame，不存在则返回空DataFrame
        """
        return self.dataframes.get(frequency, pd.DataFrame())

    def get_all_dataframes(self) -> Dict[str, pd.DataFrame]:
        """获取所有DataFrame

        Returns:
            Dict[str, pd.DataFrame]: 所有DataFrame的字典
        """
        return self.dataframes
