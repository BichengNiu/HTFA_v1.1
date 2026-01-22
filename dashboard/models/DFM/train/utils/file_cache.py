# -*- coding: utf-8 -*-
"""
文件缓存工具
提供带缓存的文件加载功能
"""

import hashlib
from typing import Any, Callable, Optional


def get_file_hash(file_obj) -> str:
    """
    计算文件对象的哈希值作为唯一标识

    Args:
        file_obj: 文件对象（如Streamlit的UploadedFile）

    Returns:
        文件的MD5哈希值
    """
    if file_obj is None:
        return ""

    return str(file_obj.file_id)


def load_cached_file(
    file_obj,
    cache_key: str,
    loader_func: Callable,
    state_manager: Any
) -> Any:
    """
    通用的带缓存文件加载函数

    Args:
        file_obj: 文件对象
        cache_key: 缓存键名
        loader_func: 加载函数，接收file_obj参数并返回加载的数据
        state_manager: 状态管理器，需要有get和set方法

    Returns:
        加载的数据（来自缓存或新加载）

    Example:
        >>> def load_csv(f):
        >>>     return pd.read_csv(f, index_col=0, parse_dates=True)
        >>>
        >>> data = load_cached_file(
        >>>     uploaded_file,
        >>>     'prepared_data',
        >>>     load_csv,
        >>>     state_manager
        >>> )
    """
    if file_obj is None:
        return None

    file_hash = get_file_hash(file_obj)
    cached_hash = state_manager.get(f'{cache_key}_hash', None)

    if cached_hash == file_hash:
        cached_data = state_manager.get(cache_key, None)
        if cached_data is not None:
            print(f"[CACHE] 使用缓存数据: {cache_key}")
            return cached_data

    print(f"[LOAD] 重新加载文件: {cache_key}")
    file_obj.seek(0)
    data = loader_func(file_obj)

    state_manager.set(cache_key, data)
    state_manager.set(f'{cache_key}_hash', file_hash)

    return data
