"""
工业数据预览子模块
"""

from dashboard.preview.modules.industrial.config import IndustrialConfig
from dashboard.preview.modules.industrial.loader import IndustrialLoader
from dashboard.preview.modules.industrial.renderer import IndustrialRenderer

__all__ = [
    'IndustrialConfig',
    'IndustrialLoader',
    'IndustrialRenderer',
]
