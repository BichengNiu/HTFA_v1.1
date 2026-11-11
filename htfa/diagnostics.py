# -*- coding: utf-8 -*-
"""
UI调试工具
提供UI组件的调试和日志功能。

调试开关由 HTFA_DEBUG_MODE 环境变量控制，
避免历史遗留的硬编码 DEBUG_ENABLED 开关。
"""

import logging
import os
import time
from typing import Dict, Optional

# 设置日志
logger = logging.getLogger(__name__)


def _debug_enabled() -> bool:
    """调试是否启用。"""
    return os.getenv('HTFA_DEBUG_MODE', 'false').strip().lower() == 'true'


def debug_log(message: str, level: str = "INFO", context: Optional[Dict] = None) -> None:
    """
    记录调试日志

    Args:
        message: 日志消息
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        context: 上下文信息
    """
    if not _debug_enabled():
        return

    timestamp = time.strftime("%H:%M:%S")
    context_str = f" | {context}" if context else ""
    log_message = f"[{timestamp}] {message}{context_str}"

    if level == "DEBUG":
        logger.debug(log_message)
    elif level == "INFO":
        logger.info(log_message)
    elif level == "WARNING":
        logger.warning(log_message)
    elif level == "ERROR":
        logger.error(log_message)
    else:
        logger.info(log_message)


def debug_button_click(button_name: str, context: Optional[Dict] = None) -> None:
    """
    记录按钮点击调试信息

    Args:
        button_name: 按钮名称
        context: 上下文信息
    """
    if not _debug_enabled():
        return

    debug_log(f"按钮点击 - {button_name}", "DEBUG", context)


# 导出的函数
__all__ = [
    'debug_log',
    'debug_button_click',
]
