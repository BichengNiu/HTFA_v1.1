# -*- coding: utf-8 -*-
"""
资源加载模块
提供统一的资源懒加载功能
"""

from dashboard.core.backend.resource.loader import (
    ResourceLoader,
    get_resource_loader
)

__all__ = [
    'ResourceLoader',
    'get_resource_loader'
]
