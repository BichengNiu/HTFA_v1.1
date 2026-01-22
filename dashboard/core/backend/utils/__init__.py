# -*- coding: utf-8 -*-
"""
工具函数和装饰器模块
"""

from dashboard.core.backend.utils.decorators import (
    safe_operation,
    validate_required_attributes
)

__all__ = [
    'safe_operation',
    'validate_required_attributes'
]
