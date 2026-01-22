"""
UI渲染器抽象基类

定义UI渲染的标准接口
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from dashboard.preview.core.base_config import BasePreviewConfig
from dashboard.preview.core.base_loader import BaseDataLoader


class BaseRenderer(ABC):
    """UI渲染器抽象基类

    定义UI渲染的标准接口

    设计原则:
    - 单一职责: 只负责UI渲染
    - 模板方法: 提供固定的渲染流程
    - 依赖倒置: 依赖抽象而非具体实现
    """

    def __init__(self, config: BasePreviewConfig, loader: BaseDataLoader):
        """初始化渲染器

        Args:
            config: 配置对象
            loader: 数据加载器对象
        """
        self.config = config
        self.loader = loader

    @abstractmethod
    def render_sidebar(self) -> Optional[Any]:
        """渲染侧边栏文件上传

        Returns:
            Optional[Any]: 上传的文件对象或None
        """
        pass

    @abstractmethod
    def render_main_content(self):
        """渲染主内容区域"""
        pass

    def render(self):
        """完整渲染流程 (模板方法)

        定义固定的执行流程,子类不应覆盖此方法

        流程:
        1. 渲染侧边栏
        2. 渲染主内容
        """
        # 1. 渲染侧边栏
        self.render_sidebar()

        # 2. 渲染主内容
        self.render_main_content()

    def get_state_key(self, key: str) -> str:
        """获取带命名空间的状态键

        Args:
            key: 状态键名

        Returns:
            str: 带命名空间的完整键名
        """
        namespace = self.loader.get_state_namespace()
        return f"{namespace}.{key}"
