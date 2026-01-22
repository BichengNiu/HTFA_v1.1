"""
基础分析组件类
提供所有分析组件的基础功能和接口
"""

import streamlit as st
import pandas as pd
import uuid
from typing import Any, Optional, Dict
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseAnalysisComponent(ABC):
    """
    基础分析组件类

    提供所有分析组件的通用功能：
    - 状态管理集成
    - 错误处理
    - 加载状态管理
    - 数据验证
    - 通用UI渲染方法
    """

    def __init__(self, state_manager):
        """
        初始化基础分析组件
        """
        self.data_loader = None
        self.component_id = str(uuid.uuid4())

        self.loading_state = {
            'is_loading': False,
            'message': ''
        }

        self.error_state = {
            'has_error': False,
            'message': ''
        }

        logger.info(f"初始化基础分析组件: {self.component_id}")

    def set_loading_state(self, is_loading: bool, message: str = ""):
        """
        设置加载状态

        Args:
            is_loading: 是否正在加载
            message: 加载消息
        """
        self.loading_state = {
            'is_loading': is_loading,
            'message': message
        }
        logger.debug(f"设置加载状态: {is_loading}, 消息: {message}")

    def set_error_state(self, has_error: bool, message: str = ""):
        """
        设置错误状态

        Args:
            has_error: 是否有错误
            message: 错误消息
        """
        self.error_state = {
            'has_error': has_error,
            'message': message
        }
        if has_error:
            logger.error(f"组件错误: {message}")
        else:
            logger.debug("清除错误状态")

    def get_data_from_state(self, key: str, default: Any = None) -> Any:
        """
        从st.session_state获取数据

        Args:
            key: 数据键
            default: 默认值

        Returns:
            获取的数据
        """
        try:
            return st.session_state.get(key, default)
        except Exception as e:
            logger.error(f"获取状态数据失败: {key}, 错误: {e}")
            return default

    def set_data_to_state(self, key: str, value: Any) -> bool:
        """
        向st.session_state设置数据

        Args:
            key: 数据键
            value: 数据值

        Returns:
            是否设置成功
        """
        try:
            st.session_state[key] = value
            return True
        except Exception as e:
            logger.error(f"设置状态数据失败: {key}, 错误: {e}")
            return False

    def validate_data(self, data: Any) -> bool:
        """
        验证数据有效性

        Args:
            data: 要验证的数据

        Returns:
            数据是否有效
        """
        if data is None:
            return False

        if isinstance(data, pd.DataFrame):
            return not data.empty

        if isinstance(data, (list, dict)):
            return len(data) > 0

        return True

    def handle_error(self, error: Exception, context: str = ""):
        """
        处理错误

        Args:
            error: 异常对象
            context: 错误上下文
        """
        error_message = f"{context}: {str(error)}" if context else str(error)
        self.set_error_state(True, error_message)

        st.error(error_message)

        logger.error(f"组件错误 [{self.component_id}]: {error_message}", exc_info=True)

    def render_loading_state(self):
        """渲染加载状态"""
        if self.loading_state['is_loading']:
            message = self.loading_state['message'] or "正在加载..."
            with st.spinner(message):
                pass

    def render_error_state(self):
        """渲染错误状态"""
        if self.error_state['has_error']:
            st.error(self.error_state['message'])

    def cleanup(self):
        """清理组件状态"""
        self.set_loading_state(False)
        self.set_error_state(False)
        logger.debug(f"清理组件状态: {self.component_id}")

    def trigger_rerun(self):
        """触发streamlit重新运行"""
        st.rerun()

    @abstractmethod
    def render(self) -> None:
        """
        渲染组件
        子类必须实现此方法
        """
        pass

    def safe_render(self) -> None:
        """
        安全渲染组件（带错误处理）
        """
        try:
            if not self.loading_state['is_loading']:
                self.set_error_state(False)

            self.render_loading_state()

            if not self.error_state['has_error'] and not self.loading_state['is_loading']:
                self.render()

            self.render_error_state()

        except Exception as e:
            self.handle_error(e, "组件渲染")

    def handle_data_update(self, data_key: str, new_data: Any):
        """
        处理数据更新

        Args:
            data_key: 数据键
            new_data: 新数据
        """
        try:
            if self.validate_data(new_data):
                success = self.set_data_to_state(data_key, new_data)
                if success:
                    logger.info(f"数据更新成功: {data_key}")
                    self.trigger_rerun()
                else:
                    raise Exception("数据保存失败")
            else:
                raise ValueError("数据验证失败")

        except Exception as e:
            self.handle_error(e, f"数据更新失败 ({data_key})")

    def get_component_info(self) -> Dict[str, Any]:
        """
        获取组件信息

        Returns:
            组件信息字典
        """
        return {
            'component_id': self.component_id,
            'component_type': self.__class__.__name__,
            'loading_state': self.loading_state,
            'error_state': self.error_state
        }
