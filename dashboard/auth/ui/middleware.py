# -*- coding: utf-8 -*-
"""
认证中间件
提供认证检查、会话管理等中间件功能
"""

import streamlit as st
from typing import Optional, Dict, Any
import logging
from datetime import datetime

# 导入认证相关模块
from dashboard.auth.authentication import AuthManager
from dashboard.auth.permissions import PermissionManager
from dashboard.auth.models import User, UserSession

# 导入持久化存储工具
from dashboard.auth.ui.utils.storage import get_auth_storage_manager


class AuthMiddleware:
    """认证中间件"""

    def __init__(self):
        """初始化认证中间件"""
        self.auth_manager = AuthManager()
        self.permission_manager = PermissionManager()
        self.logger = logging.getLogger(__name__)

    def check_authentication(self) -> tuple[bool, Optional[User]]:
        """
        检查用户认证状态（带持久化存储恢复）

        Returns:
            (是否已认证, 用户对象)
        """
        try:
            # 首先尝试从持久化存储恢复认证状态
            # self._try_restore_from_persistent_storage()  # 禁用自动恢复，每次启动都需要重新登录

            # 从session state获取会话ID
            session_id = st.session_state.get('auth.user_session_id')
            if not session_id:
                self.logger.debug("未找到有效的会话ID")
                return False, None

            # 验证会话
            is_valid, user = self.auth_manager.validate_session(session_id)

            if is_valid and user:
                # 更新用户信息到session state
                st.session_state['auth.current_user'] = user
                st.session_state['auth.user_session_id'] = session_id
                st.session_state['auth.last_activity'] = datetime.now()

                # 设置用户可访问模块
                accessible_modules = self.permission_manager.get_accessible_modules(user)
                st.session_state['auth.user_accessible_modules'] = set(accessible_modules)

                # 更新持久化存储的活动时间
                self._update_persistent_storage_activity()

                return True, user
            else:
                return False, None

        except Exception as e:
            self.logger.error(f"检查认证状态失败: {e}")
            return False, None

    def require_authentication(self, show_login=True) -> Optional[User]:
        """
        要求用户认证，如果未认证则显示登录页面

        Args:
            show_login: 是否显示登录页面

        Returns:
            用户对象或None
        """
        is_authenticated, user = self.check_authentication()

        if is_authenticated and user:
            return user

        if show_login:
            # 显示登录页面
            from dashboard.auth.ui.pages.login import render_login_page

            login_result = render_login_page()
            if login_result:
                success, login_data = login_result
                if success:
                    # 登录成功，保存会话信息
                    user = login_data['user']
                    session = login_data['session']
                    remember_me = login_data.get('remember_me', False)

                    # 存储到session_state
                    st.session_state['auth.current_user'] = user
                    st.session_state['auth.user_session_id'] = session.session_id
                    st.session_state['auth.last_activity'] = datetime.now()
                    st.session_state['auth.remember_me'] = remember_me

                    # 设置用户可访问模块
                    accessible_modules = self.permission_manager.get_accessible_modules(user)
                    st.session_state['auth.user_accessible_modules'] = set(accessible_modules)

                    # 保存到持久化存储
                    try:
                        self._save_auth_state_to_persistent_storage(session.session_id, user, remember_me)
                    except Exception as e:
                        self.logger.warning(f"保存到持久化存储失败，但不影响登录: {e}")

                    # 刷新页面以进入主应用
                    st.rerun()

            # 如果登录页面正在显示，停止后续页面渲染
            st.stop()

        return None

    def check_permission(self, user: User, module_name: str) -> bool:
        """
        检查用户是否有访问指定模块的权限

        Args:
            user: 用户对象
            module_name: 模块名称

        Returns:
            是否有权限
        """
        try:
            return self.permission_manager.has_module_access(user, module_name)
        except Exception as e:
            self.logger.error(f"检查权限失败: {e}")
            return False

    def require_permission(self, user: User, module_name: str) -> bool:
        """
        要求用户具有指定模块的访问权限

        Args:
            user: 用户对象
            module_name: 模块名称

        Returns:
            是否有权限
        """
        if not self.check_permission(user, module_name):
            st.error(f"权限不足：您无权访问「{module_name}」模块")
            st.info("如需访问权限，请联系系统管理员")
            st.stop()
            return False

        return True

    def filter_accessible_modules(self, user: User, module_config: Dict) -> Dict:
        """
        过滤用户可访问的模块配置

        Args:
            user: 用户对象
            module_config: 模块配置字典

        Returns:
            过滤后的模块配置
        """
        try:
            return self.permission_manager.filter_accessible_modules(user, module_config)
        except Exception as e:
            self.logger.error(f"过滤模块配置失败: {e}")
            return module_config

    def logout(self) -> bool:
        """
        用户登出

        Returns:
            是否登出成功
        """
        try:
            # 获取会话ID
            session_id = st.session_state.get('auth.user_session_id')

            # 从服务器端删除会话
            if session_id:
                self.auth_manager.logout(session_id)

            # 清除客户端会话信息
            self._clear_user_session()

            self.logger.info("用户登出成功")
            return True

        except Exception as e:
            self.logger.error(f"登出失败: {e}")
            return False

    def _clear_user_session(self):
        """清除用户会话信息（包括持久化存储）"""
        # 清除session_state中的认证状态
        auth_keys = [
            'auth.current_user',
            'auth.user_session_id',
            'auth.user_accessible_modules',
            'auth.last_activity',
            'auth.remember_me'
        ]
        for key in auth_keys:
            if key in st.session_state:
                del st.session_state[key]

        # 清除持久化存储
        try:
            auth_mgr = get_auth_storage_manager()
            auth_mgr.clear_auth_state()
            self.logger.debug("已清除持久化存储中的认证状态")
        except Exception as e:
            self.logger.warning(f"清除持久化存储失败: {e}")

    def _try_restore_from_persistent_storage(self) -> bool:
        """
        尝试从持久化存储恢复认证状态

        Returns:
            是否恢复成功
        """
        try:
            # 如果session state中已有认证信息，跳过恢复
            if st.session_state.get('auth.user_session_id') and st.session_state.get('auth.current_user'):
                return True

            # 尝试从持久化存储恢复
            auth_mgr = get_auth_storage_manager()
            restored_auth = auth_mgr.restore_auth_state_to_session()
            if restored_auth:
                self.logger.info(f"认证状态恢复成功: 用户 {restored_auth['user_info'].get('username', 'unknown')} "
                               f"(来源: {restored_auth.get('restored_from', 'unknown')})")
                return True
            else:
                self.logger.debug("未找到可恢复的认证状态")
                return False

        except Exception as e:
            self.logger.error(f"从持久化存储恢复认证状态失败: {e}")
            return False

    def _update_persistent_storage_activity(self):
        """更新持久化存储中的活动时间"""
        try:
            from dashboard.auth.ui.utils.storage import AuthStorageManager
            # 获取当前的记住登录设置
            remember_me = st.session_state.get('auth.remember_me', False)
            storage_type = AuthStorageManager.get_storage_type(remember_me)

            # 更新活动时间
            current_time = int(datetime.now().timestamp() * 1000)
            auth_mgr = get_auth_storage_manager()
            if hasattr(auth_mgr, 'file_storage'):
                auth_mgr.file_storage.set_item(
                    auth_mgr.AUTH_KEYS['last_activity'],
                    current_time,
                    storage_type=storage_type
                )

            self.logger.debug(f"已更新持久化存储活动时间({storage_type})")

        except Exception as e:
            self.logger.warning(f"更新持久化存储活动时间失败: {e}")

    def _save_auth_state_to_persistent_storage(self, session_id: str, user: User, remember_me: bool = False) -> bool:
        """
        保存认证状态到持久化存储

        Args:
            session_id: 会话ID
            user: 用户对象
            remember_me: 是否记住登录

        Returns:
            是否保存成功
        """
        try:
            # 将用户对象转换为字典
            user_info = user.to_dict()

            # 保存到持久化存储
            auth_mgr = get_auth_storage_manager()
            success = auth_mgr.save_auth_state(session_id, user_info, remember_me)
            if success:
                self.logger.info(f"认证状态已保存到持久化存储: 用户 {user.username}, 记住登录: {remember_me}")
            else:
                self.logger.warning(f"保存认证状态到持久化存储失败")

            return success

        except Exception as e:
            self.logger.error(f"保存认证状态到持久化存储异常: {e}")
            return False

    def get_current_user(self) -> Optional[User]:
        """
        获取当前登录用户

        Returns:
            用户对象或None
        """
        return st.session_state.get('auth.current_user')

    def is_authenticated(self) -> bool:
        """
        检查是否已认证

        Returns:
            是否已认证
        """
        is_auth, _ = self.check_authentication()
        return is_auth


def get_auth_middleware() -> AuthMiddleware:
    """获取认证中间件实例"""
    if '_auth_middleware' not in st.session_state:
        st.session_state['_auth_middleware'] = AuthMiddleware()
    return st.session_state['_auth_middleware']
