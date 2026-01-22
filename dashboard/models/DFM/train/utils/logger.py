# -*- coding: utf-8 -*-
"""
日志工具模块
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = 'WARNING',
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> None:
    """设置日志配置

    Args:
        level: 日志级别
        log_file: 日志文件路径
        format_string: 日志格式
    """
    if format_string is None:
        format_string = '%(levelname)s: %(message)s'

    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=handlers
    )


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
