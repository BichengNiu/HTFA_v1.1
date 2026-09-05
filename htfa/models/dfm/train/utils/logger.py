# -*- coding: utf-8 -*-
"""
日志工具模块
"""

import logging
from typing import Optional


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """获取logger实例

    Args:
        name: logger名称
        level: 日志级别

    Returns:
        logging.Logger: logger实例
    """
    logger = logging.getLogger(name)

    if level:
        logger.setLevel(getattr(logging, level.upper()))

    return logger
