# -*- coding: utf-8 -*-
"""
日志配置模块

为DFM Decomp模块提供统一的日志配置。
"""

import logging
from typing import Optional


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    获取配置好的日志记录器

    Args:
        name: 日志记录器名称（通常使用模块名）
        level: 日志级别，默认为INFO

    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '[%(name)s] %(levelname)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if level is not None:
        logger.setLevel(level)
    elif logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

    return logger
