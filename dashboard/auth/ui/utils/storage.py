# -*- coding: utf-8 -*-
"""
认证相关的持久化存储管理
简化实现,不依赖core模块
"""

import streamlit as st
import logging
import time
import json
import tempfile
import hashlib
from typing import Any, Optional, Dict
from pathlib import Path


class SimpleFileStorage:
    """简化的文件存储实现"""

    def __init__(self):
        self.storage_dir = Path(tempfile.gettempdir()) / "htfa_auth_storage"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def _get_file_path(self, key: str, storage_type: str) -> Path:
        """获取存储文件路径"""
        # 创建安全的文件名
        safe_key = hashlib.md5(key.encode()).hexdigest()
        filename = f"{storage_type}_{safe_key}.json"
        return self.storage_dir / filename

    def set_item(self, key: str, value: Any, storage_type: str = "local") -> bool:
        """设置存储项"""
        try:
            file_path = self._get_file_path(key, storage_type)
            storage_data = {
                'key': key,
                'value': value,
                'timestamp': int(time.time() * 1000)
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, default=str, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"设置存储失败: {key}, 错误: {e}")
            return False

    def get_item(self, key: str, default: Any = None, storage_type: str = "local") -> Any:
        """获取存储项"""
        try:
            file_path = self._get_file_path(key, storage_type)
            if not file_path.exists():
                return default

            with open(file_path, 'r', encoding='utf-8') as f:
                storage_data = json.load(f)

            if 'value' not in storage_data:
                return default

            # 检查过期(7天)
            max_age = 7 * 24 * 60 * 60 * 1000
            current_time = int(time.time() * 1000)
            if current_time - storage_data.get('timestamp', 0) > max_age:
                file_path.unlink(missing_ok=True)
                return default

            return storage_data['value']
        except Exception as e:
            self.logger.error(f"获取存储失败: {key}, 错误: {e}")
            return default

    def remove_item(self, key: str, storage_type: str = "local") -> bool:
        """移除存储项"""
        try:
            file_path = self._get_file_path(key, storage_type)
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            self.logger.error(f"移除存储失败: {key}, 错误: {e}")
            return False


class AuthStorageManager:
    """认证相关的持久化存储管理器"""

    def __init__(self):
        """初始化认证存储管理器"""
        self.file_storage = SimpleFileStorage()
        self.logger = logging.getLogger(__name__)

        # 认证相关的存储键名
        self.AUTH_KEYS = {
            'session_id': 'htfa_user_session_id',
            'user_info': 'htfa_current_user',
            'last_activity': 'htfa_last_activity',
            'remember_me': 'htfa_remember_me',
            'login_timestamp': 'htfa_login_timestamp'
        }

    @staticmethod
    def get_storage_type(remember_me: bool) -> str:
        """根据remember_me标识选择存储类型"""
        return "local" if remember_me else "session"

    def save_auth_state(self, session_id: str, user_info: Dict[str, Any],
                       remember_me: bool = False) -> bool:
        """
        保存认证状态到持久化存储

        Args:
            session_id: 会话ID
            user_info: 用户信息字典
            remember_me: 是否记住登录

        Returns:
            是否保存成功
        """
        try:
            current_time = int(time.time() * 1000)
            storage_type = self.get_storage_type(remember_me)
            success_count = 0

            # 保存到文件存储
            storage_items = {
                self.AUTH_KEYS['session_id']: session_id,
                self.AUTH_KEYS['user_info']: user_info,
                self.AUTH_KEYS['last_activity']: current_time,
                self.AUTH_KEYS['remember_me']: remember_me,
                self.AUTH_KEYS['login_timestamp']: current_time
            }

            for key, value in storage_items.items():
                if self.file_storage.set_item(key, value, storage_type):
                    success_count += 1

            # 同时保存到session_state
            st.session_state['auth.user_session_id'] = session_id
            st.session_state['auth.current_user'] = user_info
            st.session_state['auth.last_activity'] = current_time
            st.session_state['auth.remember_me'] = remember_me
            st.session_state['auth.login_timestamp'] = current_time

            return success_count >= 3

        except Exception as e:
            self.logger.error(f"保存认证状态失败: {e}")
            return False

    def restore_auth_state_to_session(self) -> Optional[Dict[str, Any]]:
        """
        从持久化存储恢复认证状态到session_state

        Returns:
            恢复的认证信息字典,失败则返回None
        """
        try:
            # 检查session_state中是否已有有效认证信息
            if st.session_state.get('auth.user_session_id') and st.session_state.get('auth.current_user'):
                return {
                    'session_id': st.session_state['auth.user_session_id'],
                    'user_info': st.session_state['auth.current_user'],
                    'restored_from': 'session_state'
                }

            # 从文件存储恢复
            restored_auth = self._restore_from_file_storage()
            if restored_auth:
                self._apply_restored_auth_to_session(restored_auth)
                return restored_auth

            return None

        except Exception as e:
            self.logger.error(f"恢复认证状态失败: {e}")
            return None

    def _restore_from_file_storage(self) -> Optional[Dict[str, Any]]:
        """从文件存储恢复认证状态"""
        try:
            for storage_type in ["local", "session"]:
                session_id = self.file_storage.get_item(self.AUTH_KEYS['session_id'], storage_type=storage_type)
                user_info = self.file_storage.get_item(self.AUTH_KEYS['user_info'], storage_type=storage_type)

                if session_id and user_info:
                    login_timestamp = self.file_storage.get_item(
                        self.AUTH_KEYS['login_timestamp'],
                        default=int(time.time() * 1000),
                        storage_type=storage_type
                    )
                    remember_me = self.file_storage.get_item(
                        self.AUTH_KEYS['remember_me'],
                        default=False,
                        storage_type=storage_type
                    )

                    # 检查过期
                    max_age = 7 * 24 * 60 * 60 * 1000 if remember_me else 24 * 60 * 60 * 1000
                    current_time = int(time.time() * 1000)

                    if current_time - login_timestamp < max_age:
                        return {
                            'session_id': session_id,
                            'user_info': user_info,
                            'last_activity': self.file_storage.get_item(
                                self.AUTH_KEYS['last_activity'],
                                default=current_time,
                                storage_type=storage_type
                            ),
                            'remember_me': remember_me,
                            'login_timestamp': login_timestamp,
                            'restored_from': 'file_storage'
                        }
                    else:
                        # 会话已过期,清除存储
                        self._clear_storage_type(storage_type)

            return None

        except Exception as e:
            self.logger.error(f"从文件存储恢复失败: {e}")
            return None

    def _apply_restored_auth_to_session(self, auth_data: Dict[str, Any]):
        """将恢复的认证数据应用到session_state"""
        try:
            st.session_state['auth.user_session_id'] = auth_data['session_id']
            st.session_state['auth.current_user'] = auth_data['user_info']
            st.session_state['auth.last_activity'] = auth_data.get('last_activity', int(time.time() * 1000))
            st.session_state['auth.remember_me'] = auth_data.get('remember_me', False)
        except Exception as e:
            self.logger.error(f"应用认证状态到session_state失败: {e}")

    def clear_auth_state(self) -> bool:
        """清除所有认证状态"""
        try:
            success_count = 0

            # 清除文件存储
            for storage_type in ["local", "session"]:
                cleared_count = self._clear_storage_type(storage_type)
                success_count += cleared_count

            # 清除session_state
            session_keys = [
                'auth.user_session_id',
                'auth.current_user',
                'auth.last_activity',
                'auth.remember_me',
                'auth.login_timestamp'
            ]
            for key in session_keys:
                if key in st.session_state:
                    del st.session_state[key]
                    success_count += 1

            return success_count > 0

        except Exception as e:
            self.logger.error(f"清除认证状态失败: {e}")
            return False

    def _clear_storage_type(self, storage_type: str) -> int:
        """清除指定类型的存储"""
        cleared_count = 0
        for key in self.AUTH_KEYS.values():
            if self.file_storage.remove_item(key, storage_type):
                cleared_count += 1
        return cleared_count


# 工厂函数
def get_auth_storage_manager() -> AuthStorageManager:
    """获取当前session的认证存储管理器实例"""
    if '_auth_storage_manager' not in st.session_state:
        st.session_state['_auth_storage_manager'] = AuthStorageManager()
    return st.session_state['_auth_storage_manager']
