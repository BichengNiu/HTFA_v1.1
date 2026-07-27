"""
领域模型定义

定义数据预览相关的数据结构
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, Any, List, Optional
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

    def to_dict(self) -> Dict[str, Any]:
        """返回便于状态存储和展示的字典。"""
        return asdict(self)


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

    # 额外的自定义映射(可扩展)
    custom_maps: Dict[str, Dict[str, Any]] = field(default_factory=dict)

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

    def get_all_maps(self) -> Dict[str, Dict[str, Any]]:
        """获取所有映射字典

        Returns:
            Dict[str, Dict[str, str]]: 所有映射字典
        """
        return {
            'source': self.source_map,
            'industry': self.indicator_industry_map,
            'unit': self.indicator_unit_map,
            'type': self.indicator_type_map,
            'freq': self.indicator_freq_map,
            'metadata': self.indicator_metadata_map,
        }

    def has_frequency(self, frequency: str) -> bool:
        """检查是否存在指定频率的数据

        Args:
            frequency: 频率名称

        Returns:
            bool: 是否存在该频率的数据
        """
        df = self.dataframes.get(frequency)
        return df is not None and not df.empty

    def get_available_frequencies(self) -> List[str]:
        """获取所有可用的频率

        Returns:
            List[str]: 可用频率列表
        """
        return [freq for freq in self.dataframes.keys() if not self.dataframes[freq].empty]

    def get_indicators_by_frequency(self, frequency: str) -> List[str]:
        """获取指定频率的所有指标

        Args:
            frequency: 频率名称

        Returns:
            List[str]: 指标名称列表
        """
        df = self.get_dataframe(frequency)
        if df.empty:
            return []

        return df.columns.tolist()

    def get_indicator_metadata(self, indicator: str) -> Dict[str, Any]:
        """获取指标的元数据

        Args:
            indicator: 指标名称

        Returns:
            Dict[str, str]: 指标元数据(行业、单位、类型等)
        """
        metadata = self.indicator_metadata_map.get(indicator)
        if metadata is not None:
            return metadata.to_dict()

        return {
            'indicator_name': indicator,
            'industry': self.indicator_industry_map.get(indicator, '未知'),
            'unit': self.indicator_unit_map.get(indicator, ''),
            'indicator_type': self.indicator_type_map.get(indicator, ''),
            'physical_source': self.source_map.get(indicator, ''),
        }

    def __repr__(self) -> str:
        """字符串表示

        Returns:
            str: 对象的字符串表示
        """
        freqs = self.get_available_frequencies()
        total_indicators = sum(len(self.get_indicators_by_frequency(f)) for f in freqs)
        return (
            f"LoadedPreviewData(module='{self.module_name}', "
            f"frequencies={freqs}, "
            f"total_indicators={total_indicators})"
        )
