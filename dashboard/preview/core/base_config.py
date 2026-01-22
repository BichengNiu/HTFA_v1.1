"""
配置抽象基类

定义所有数据预览子模块的配置接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
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


class BasePreviewConfig(ABC):
    """预览配置抽象基类

    所有子模块配置必须继承此类并实现抽象方法

    设计原则:
    - 单一职责: 只负责配置管理
    - 开放封闭: 通过继承扩展,无需修改基类
    """

    @abstractmethod
    def get_frequencies(self) -> List[str]:
        """返回支持的频率列表 (英文名)

        Returns:
            List[str]: 频率英文名列表 (如 ['weekly', 'monthly'])
        """
        pass

    @abstractmethod
    def get_frequency_config(self, freq: str) -> FrequencyConfig:
        """获取指定频率的配置

        Args:
            freq: 频率英文名 (如 'weekly')

        Returns:
            FrequencyConfig: 频率配置对象
        """
        pass

    @abstractmethod
    def get_colors(self) -> Dict[str, str]:
        """获取颜色配置

        Returns:
            Dict[str, str]: 颜色配置字典
        """
        pass

    @abstractmethod
    def get_ui_text(self) -> Dict[str, str]:
        """获取UI文本配置

        Returns:
            Dict[str, str]: UI文本配置字典
        """
        pass

    @abstractmethod
    def get_plot_config(self) -> Dict[str, Any]:
        """获取绘图配置

        Returns:
            Dict[str, Any]: 绘图配置字典
        """
        pass

    @abstractmethod
    def get_summary_config(self) -> Dict[str, Any]:
        """获取摘要配置

        Returns:
            Dict[str, Any]: 摘要配置字典
        """
        pass

    def get_frequency_order(self) -> List[str]:
        """获取频率显示顺序 (中文名)

        子类可覆盖以自定义顺序

        Returns:
            List[str]: 频率中文名列表
        """
        return ['日度', '周度', '旬度', '月度', '季度', '年度']

    def get_chinese_to_english_freq(self) -> Dict[str, str]:
        """获取中文到英文频率映射

        子类可覆盖以自定义映射

        Returns:
            Dict[str, str]: 中英文频率映射
        """
        return {
            '周度': 'weekly',
            '月度': 'monthly',
            '日度': 'daily',
            '旬度': 'ten_day',
            '季度': 'quarterly',
            '年度': 'yearly'
        }

    def get_english_to_chinese_freq(self) -> Dict[str, str]:
        """获取英文到中文频率映射

        Returns:
            Dict[str, str]: 英中文频率映射
        """
        return {v: k for k, v in self.get_chinese_to_english_freq().items()}
