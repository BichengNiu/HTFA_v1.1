# -*- coding: utf-8 -*-
"""
认证中间件
提供认证检查、会话管理等中间件功能
"""

import streamlit as st
from typing import Optional
import logging
from datetime import datetime

# 导入认证相关模块
from dashboard.auth.authentication import AuthManager
from dashboard.auth.database import AuthDatabase
from dashboard.auth.permissions import PermissionManager
from dashboard.auth.models import User


class AuthMiddleware:
    """认证中间件"""

    def __init__(self, database: AuthDatabase | None = None):
        """初始化认证中间件"""
        database = database or AuthDatabase()
        self.auth_manager = AuthManager(db=database)
        self.permission_manager = PermissionManager()
        self.logger = logging.getLogger(__name__)

    def check_authentication(self) -> tuple[bool, Optional[User]]:
        """
        检查当前 Streamlit 会话中的用户认证状态。

        Returns:
            (是否已认证, 用户对象)
        """
        try:
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

            login_result = render_login_page(self.auth_manager)
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

                    # 刷新页面以进入主应用
                    st.rerun()

            # 如果登录页面正在显示，停止后续页面渲染
            st.stop()

        return None


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
        """清除当前 Streamlit 会话中的认证状态。"""
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



def get_auth_middleware() -> AuthMiddleware:
    """获取认证中间件实例"""
    if '_auth_middleware' not in st.session_state:
        st.session_state['_auth_middleware'] = AuthMiddleware()
    return st.session_state['_auth_middleware']
