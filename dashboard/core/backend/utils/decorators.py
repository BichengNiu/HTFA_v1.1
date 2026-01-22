# -*- coding: utf-8 -*-
"""
Core基础设施模块
提供统一的装饰器、基类和通用工具
"""

import threading
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


# ==================== 工具函数 ====================

def _get_logger_from_args(args: tuple):
    """
    从函数参数中获取日志记录器

    Args:
        args: 函数参数元组

    Returns:
        日志记录器实例
    """
    if args and hasattr(args[0], 'logger'):
        return args[0].logger
    return logger


# ==================== 装饰器 ====================

def safe_operation(default_return: Any = None, log_error: bool = True):
    """
    安全操作装饰器 - 统一异常处理

    Args:
        default_return: 发生异常时的默认返回值
        log_error: 是否记录错误日志

    Usage:
        @safe_operation(default_return=False)
        def some_method(self, key, value):
            return True
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    target_logger = _get_logger_from_args(args)
                    target_logger.error(f"Operation '{func.__name__}' failed: {e}")
                return default_return
        return wrapper
    return decorator




# ==================== 工具函数 ====================

def validate_required_attributes(obj: Any, *attrs: str):
    """
    验证对象是否具有必需的属性

    Args:
        obj: 待验证对象
        *attrs: 必需的属性名列表

    Raises:
        AttributeError: 如果缺少必需属性
    """
    missing_attrs = [attr for attr in attrs if not hasattr(obj, attr)]
    if missing_attrs:
        raise AttributeError(
            f"Object {obj.__class__.__name__} missing required attributes: {', '.join(missing_attrs)}"
        )
