"""
数据加载器抽象基类

定义数据加载的标准流程
"""

from abc import ABC, abstractmethod
from typing import Any, List


class BaseDataLoader(ABC):
    """数据加载器抽象基类

    定义数据加载的标准流程

    设计原则:
    - 单一职责: 只负责数据加载和初步处理
    - 依赖倒置: 依赖配置抽象而非具体配置
    """

    @abstractmethod
    def load_and_process_data(self, files: List[Any]) -> Any:
        """加载并处理数据

        Args:
            files: 文件对象列表 (通常是Streamlit的UploadedFile)

        Returns:
            LoadedPreviewData: 标准化的数据对象

        Raises:
            ValueError: 数据加载或处理失败时
        """
        pass

    @abstractmethod
    def extract_industry_name(self, source: str) -> str:
        """从数据源提取行业名称

        Args:
            source: 数据源字符串

        Returns:
            str: 行业名称
        """
        pass

    @abstractmethod
    def get_state_namespace(self) -> str:
        """获取状态命名空间

        用于在session_state中隔离不同子模块的状态

        Returns:
            str: 状态命名空间前缀 (如 'preview.industrial')
        """
        pass
