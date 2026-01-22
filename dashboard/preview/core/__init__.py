"""
数据预览核心抽象层

提供配置、数据加载、UI渲染的抽象基类
"""

from dashboard.preview.core.base_config import BasePreviewConfig, FrequencyConfig
from dashboard.preview.core.base_loader import BaseDataLoader
from dashboard.preview.core.base_renderer import BaseRenderer

__all__ = [
    'BasePreviewConfig',
    'FrequencyConfig',
    'BaseDataLoader',
    'BaseRenderer',
]
