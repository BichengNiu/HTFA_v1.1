# -*- coding: utf-8 -*-
"""
序列化检查工具

用于在并行执行前验证参数的可序列化性
"""

import pickle
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def check_picklable(obj: Any, name: str = "object") -> Tuple[bool, str]:
    """
    检查对象是否可以被pickle序列化

    Args:
        obj: 待检查的对象
        name: 对象名称（用于错误信息）

    Returns:
        (是否可序列化, 错误信息)
    """
    try:
        pickle.dumps(obj)
        return (True, "")
    except Exception as e:
        error_msg = f"{name} 不可序列化: {type(e).__name__}: {str(e)}"
        return (False, error_msg)


def check_dict_picklable(params: Dict[str, Any], dict_name: str = "params") -> Tuple[bool, List[str]]:
    """
    检查字典中所有键值对的可序列化性

    Args:
        params: 参数字典
        dict_name: 字典名称（用于错误信息）

    Returns:
        (是否全部可序列化, 不可序列化的键列表)
    """
    unpicklable_keys = []

    for key, value in params.items():
        is_picklable, error_msg = check_picklable(value, f"{dict_name}['{key}']")
        if not is_picklable:
            unpicklable_keys.append(key)
            logger.warning(error_msg)

    return (len(unpicklable_keys) == 0, unpicklable_keys)


def get_object_size_info(obj: Any) -> str:
    """
    获取对象的序列化大小信息

    Args:
        obj: 待检查的对象

    Returns:
        大小信息字符串
    """
    try:
        serialized = pickle.dumps(obj)
        size_bytes = len(serialized)

        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
    except Exception as e:
        return f"无法序列化: {e}"


__all__ = [
    'check_picklable',
    'check_dict_picklable',
    'get_object_size_info'
]
