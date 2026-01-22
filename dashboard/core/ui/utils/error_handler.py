# -*- coding: utf-8 -*-
"""
UI错误处理器
提供简单的错误显示和日志记录功能
"""

import logging
import traceback
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def handle_error(error: Exception, st_obj, context: str = "",
                component_id: str = "", show_details: bool = False) -> None:
    """
    处理UI错误

    Args:
        error: 异常对象
        st_obj: Streamlit对象
        context: 错误上下文
        component_id: 组件ID
        show_details: 是否显示详细错误信息
    """
    try:
        error_type = type(error).__name__
        error_message = str(error)

        # 构建日志消息
        log_msg = f"UI错误"
        if component_id:
            log_msg += f" [组件:{component_id}]"
        if context:
            log_msg += f" [上下文:{context}]"
        log_msg += f" - {error_type}: {error_message}"

        # 记录日志
        logger.error(log_msg)

        # 显示用户友好的错误消息
        user_message = _get_user_friendly_message(error_type, error_message)
        st_obj.error(user_message)

        # 在调试模式下显示详细信息
        if show_details or st_obj.session_state.get('debug_mode', False):
            with st_obj.expander("详细错误信息"):
                st_obj.text(f"错误类型: {error_type}")
                st_obj.text(f"错误消息: {error_message}")
                if component_id:
                    st_obj.text(f"组件ID: {component_id}")
                if context:
                    st_obj.text(f"上下文: {context}")
                st_obj.text(f"时间: {datetime.now().isoformat()}")
                st_obj.code(traceback.format_exc(), language="python")

    except Exception as handling_error:
        # 错误处理本身出错时的兜底处理
        logger.error(f"错误处理失败: {handling_error}")
        st_obj.error(f"发生错误: {str(error)}")


def _get_user_friendly_message(error_type: str, error_message: str) -> str:
    """
    获取用户友好的错误消息

    Args:
        error_type: 错误类型
        error_message: 原始错误消息

    Returns:
        用户友好的错误消息
    """
    # 常见错误类型的友好消息
    friendly_messages = {
        'FileNotFoundError': '文件未找到，请检查文件路径是否正确',
        'PermissionError': '权限不足，无法访问该文件',
        'ValueError': '数据格式错误，请检查输入数据',
        'TypeError': '数据类型错误，请检查输入数据的类型',
        'KeyError': '缺少必要的数据字段',
        'ConnectionError': '网络连接错误，请检查网络连接',
        'TimeoutError': '操作超时，请稍后重试',
        'MemoryError': '内存不足，请关闭其他程序或处理较小的数据集',
    }

    message = friendly_messages.get(error_type, '操作失败')

    # 如果原始消息较短且有意义，添加到友好消息后面
    if error_message and len(error_message) < 100:
        message += f": {error_message}"

    return message


class UIErrorHandler:
    """UI错误处理器类"""

    def handle_ui_error(self, error: Exception, component_id: str = "",
                       context: str = "", st_obj=None, **kwargs) -> dict:
        """
        处理UI错误并返回结果字典

        Args:
            error: 异常对象
            component_id: 组件ID
            context: 错误上下文
            st_obj: Streamlit对象
            **kwargs: 其他参数

        Returns:
            包含success和error_info的字典
        """
        try:
            error_type = type(error).__name__
            error_message = str(error)

            # 构建错误信息
            error_info = {
                'type': error_type,
                'message': error_message,
                'component_id': component_id,
                'context': context,
                'timestamp': datetime.now().isoformat()
            }

            # 如果提供了st_obj，使用handle_error显示错误
            if st_obj:
                handle_error(
                    error=error,
                    st_obj=st_obj,
                    context=context,
                    component_id=component_id,
                    show_details=kwargs.get('show_details', False)
                )

            return {
                'success': True,
                'error_info': error_info
            }

        except Exception as handling_error:
            logger.error(f"UI错误处理失败: {handling_error}")
            return {
                'success': False,
                'error_info': {
                    'type': 'ErrorHandlingError',
                    'message': str(handling_error)
                }
            }


# 全局错误处理器实例
_error_handler = None


def get_ui_error_handler() -> UIErrorHandler:
    """
    获取UI错误处理器单例

    Returns:
        UIErrorHandler实例
    """
    global _error_handler
    if _error_handler is None:
        _error_handler = UIErrorHandler()
    return _error_handler


