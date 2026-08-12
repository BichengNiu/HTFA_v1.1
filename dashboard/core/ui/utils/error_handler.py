"""Streamlit 页面错误的统一展示函数。"""

from __future__ import annotations

from datetime import datetime
import logging
import traceback
from typing import Any

logger = logging.getLogger(__name__)


FRIENDLY_MESSAGES = {
    "FileNotFoundError": "文件未找到，请检查文件路径是否正确",
    "PermissionError": "权限不足，无法访问该文件",
    "ValueError": "数据格式错误，请检查输入数据",
    "TypeError": "数据类型错误，请检查输入数据的类型",
    "KeyError": "缺少必要的数据字段",
    "ConnectionError": "网络连接错误，请检查网络连接",
    "TimeoutError": "操作超时，请稍后重试",
    "MemoryError": "内存不足，请关闭其他程序或处理较小的数据集",
}


def handle_ui_error(
    error: Exception,
    st_obj: Any,
    *,
    context: str = "",
    component_id: str = "",
    show_details: bool = False,
) -> dict[str, Any]:
    """记录并展示异常，同时返回可保存到会话状态的错误信息。"""

    error_type = type(error).__name__
    error_message = str(error)
    error_info = {
        "type": error_type,
        "message": error_message,
        "component_id": component_id,
        "context": context,
        "timestamp": datetime.now().isoformat(),
    }
    logger.error(
        "UI错误 [组件:%s] [上下文:%s] - %s: %s",
        component_id,
        context,
        error_type,
        error_message,
    )

    message = FRIENDLY_MESSAGES.get(error_type, "操作失败")
    if error_message and len(error_message) < 100:
        message = f"{message}: {error_message}"
    st_obj.error(message)

    debug_mode = st_obj.session_state.get("auth.debug_mode", False)
    if show_details or debug_mode:
        with st_obj.expander("详细错误信息"):
            st_obj.text(f"错误类型: {error_type}")
            st_obj.text(f"错误消息: {error_message}")
            if component_id:
                st_obj.text(f"组件ID: {component_id}")
            if context:
                st_obj.text(f"上下文: {context}")
            st_obj.text(f"时间: {error_info['timestamp']}")
            st_obj.code(traceback.format_exc(), language="python")

    return {"success": True, "error_info": error_info}


__all__ = ["handle_ui_error"]
