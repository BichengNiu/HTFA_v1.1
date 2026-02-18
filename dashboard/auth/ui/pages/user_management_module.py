# -*- coding: utf-8 -*-
"""
用户管理主模块页面
"""

import streamlit as st
from typing import Optional

# 导入认证相关组件
from dashboard.auth.ui.pages.user_management import render_user_management_page
from dashboard.auth.ui.middleware import get_auth_middleware


def _check_user_management_access():
    """
    检查用户管理模块的访问权限

    Returns:
        tuple: (can_access: bool, current_user, error_type: str|None)
        error_type: None=可访问, 'no_auth'=未认证, 'no_permission'=权限不足
    """
    auth_middleware = get_auth_middleware()
    debug_mode = st.session_state.get('auth.debug_mode', False)
    current_user = st.session_state.get("auth.current_user", None)

    if debug_mode:
        st.info("调试模式：已自动授予管理员权限")
        return True, current_user, None

    if not current_user:
        return False, None, 'no_auth'

    if not auth_middleware.permission_manager.is_admin(current_user):
        return False, current_user, 'no_permission'

    return True, current_user, None


def _render_no_auth_message(button_key: str = "login_btn"):
    """渲染未认证提示"""
    st.warning("请先登录以访问用户管理功能")
    st.info("用户管理功能需要管理员权限")
    if st.button("点击登录", key=button_key, type="primary"):
        for key in st.session_state.keys():
            if key.startswith('user_') or key.startswith('auth_'):
                del st.session_state[key]
        st.rerun()
def _render_no_permission_message(current_user):
    """渲染权限不足提示"""
    st.error("权限不足：只有管理员可以访问用户管理功能")
    st.info("如需管理权限，请联系系统管理员")

    auth_middleware = get_auth_middleware()
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**用户名：** {current_user.username}")
        st.write(f"**邮箱：** {current_user.email or '未设置'}")
    with col2:
        accessible_modules = auth_middleware.permission_manager.get_accessible_modules(current_user)
        if accessible_modules:
            st.write(f"**可访问模块：** {', '.join(accessible_modules)}")
        else:
            st.write("**可访问模块：** 无")


class UserManagementWelcomePage:
    """用户管理欢迎页面"""

    @staticmethod
    def render():
        """渲染用户管理欢迎页面"""
        try:
            can_access, current_user, error_type = _check_user_management_access()

            if error_type == 'no_auth':
                _render_no_auth_message()
                st.markdown("---")
                st.markdown("### 功能概览")
                st.markdown("- **用户列表管理** - 查看和管理所有系统用户")
                st.markdown("- **添加新用户** - 创建新的系统账户")
                st.markdown('- **权限配置** - 管理用户直接权限')
                st.markdown("- **系统统计** - 查看用户活动统计信息")
                return

            if error_type == 'no_permission':
                _render_no_permission_message(current_user)
                return

            render_user_management_page(current_user)

        except Exception as e:
            st.error(f"用户管理模块初始化失败: {e}")
            raise


def render_user_management_sub_module(sub_module_name: str) -> Optional[str]:
    """渲染用户管理子模块"""
    try:
        st.markdown(f"### {sub_module_name}")

        can_access, current_user, error_type = _check_user_management_access()

        if error_type == 'no_auth':
            _render_no_auth_message(button_key=f"login_btn_{sub_module_name}")
            return "用户未认证"

        if error_type == 'no_permission':
            with st.expander("当前用户信息", expanded=False):
                _render_no_permission_message(current_user)
            return "权限不足"

        valid_sub_modules = ("用户列表", "权限配置", "权限设置", "系统设置")
        if sub_module_name not in valid_sub_modules:
            st.error(f"未知的用户管理子模块: {sub_module_name}")
            st.info(f"可用的子模块: {', '.join(valid_sub_modules)}")
            return f"未知子模块: {sub_module_name}"

        render_user_management_page(current_user)
        return "success"

    except Exception as e:
        st.error(f"渲染用户管理子模块失败: {e}")
        raise
