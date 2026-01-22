# -*- coding: utf-8 -*-
"""
UI调试工具
提供UI组件的调试和日志功能
"""

import logging
import time
from typing import Any, Dict, Optional

# 设置日志
logger = logging.getLogger(__name__)

# 调试开关
DEBUG_ENABLED = False

def debug_log(message: str, level: str = "INFO", context: Optional[Dict[str, Any]] = None) -> None:
    """
    记录调试日志
    
    Args:
        message: 日志消息
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        context: 上下文信息
    """
    if not DEBUG_ENABLED:
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

def debug_state_change(component: str, key: str, old_value: Any, new_value: Any) -> None:
    """
    记录状态变化调试信息
    
    Args:
        component: 组件名称
        key: 状态键
        old_value: 旧值
        new_value: 新值
    """
    if not DEBUG_ENABLED:
        return
    
    debug_log(
        f"状态变化 - {component}",
        "DEBUG",
        {"key": key, "old": old_value, "new": new_value}
    )

def debug_navigation(action: str, details: str = "") -> None:
    """
    记录导航调试信息
    
    Args:
        action: 导航动作
        details: 详细信息
    """
    if not DEBUG_ENABLED:
        return
    
    debug_log(f"导航 - {action}: {details}", "DEBUG")

def debug_button_click(button_name: str, context: Optional[Dict[str, Any]] = None) -> None:
    """
    记录按钮点击调试信息
    
    Args:
        button_name: 按钮名称
        context: 上下文信息
    """
    if not DEBUG_ENABLED:
        return
    
    debug_log(f"按钮点击 - {button_name}", "DEBUG", context)

def enable_debug() -> None:
    """启用调试模式"""
    global DEBUG_ENABLED
    DEBUG_ENABLED = True
    logger.setLevel(logging.DEBUG)

def disable_debug() -> None:
    """禁用调试模式"""
    global DEBUG_ENABLED
    DEBUG_ENABLED = False

def is_debug_enabled() -> bool:
    """检查是否启用调试模式"""
    return DEBUG_ENABLED

# 导出的函数
__all__ = [
    'debug_log',
    'debug_state_change', 
    'debug_navigation',
    'debug_button_click',
    'enable_debug',
    'disable_debug',
    'is_debug_enabled'
]
