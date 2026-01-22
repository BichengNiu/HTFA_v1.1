"""
领域模型定义

定义数据预览相关的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import pandas as pd


@dataclass
class LoadedPreviewData:
    """预览数据加载结果的通用封装

    替代原来的LoadedIndustrialData，更通用化

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

    def get_all_maps(self) -> Dict[str, Dict[str, str]]:
        """获取所有映射字典

        Returns:
            Dict[str, Dict[str, str]]: 所有映射字典
        """
        return {
            'source': self.source_map,
            'industry': self.indicator_industry_map,
            'unit': self.indicator_unit_map,
            'type': self.indicator_type_map,
            'freq': self.indicator_freq_map
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

        # 假设第一列是指标名称列
        indicator_column = df.columns[0]
        return df[indicator_column].unique().tolist()

    def get_indicator_metadata(self, indicator: str) -> Dict[str, str]:
        """获取指标的元数据

        Args:
            indicator: 指标名称

        Returns:
            Dict[str, str]: 指标元数据(行业、单位、类型等)
        """
        return {
            'industry': self.indicator_industry_map.get(indicator, '未知'),
            'unit': self.indicator_unit_map.get(indicator, ''),
            'type': self.indicator_type_map.get(indicator, ''),
            'source': self.source_map.get(indicator, '')
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
