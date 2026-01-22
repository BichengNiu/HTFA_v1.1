# -*- coding: utf-8 -*-
"""
用户管理主模块页面
"""

import streamlit as st
from typing import Optional

# 导入认证相关组件
from dashboard.auth.ui.pages.user_management import render_user_management_page
from dashboard.auth.ui.middleware import get_auth_middleware


class UserManagementWelcomePage:
    """用户管理欢迎页面"""

    @staticmethod
    def render():
        """渲染用户管理欢迎页面"""

        try:
            # 检查函数是否成功导入
            if get_auth_middleware is None:
                st.error("认证中间件未正确导入")
                return

            # 获取认证中间件
            auth_middleware = get_auth_middleware()

            # 检查调试模式
            debug_mode = st.session_state.get('auth.debug_mode', False)

            # 从统一状态管理器获取当前用户（避免重复认证）
            current_user = st.session_state.get("auth.current_user", None)

            # 调试模式：跳过认证和权限检查
            if debug_mode:
                st.info("调试模式：已自动授予管理员权限")
                # 在调试模式下直接渲染用户管理页面
                if render_user_management_page is None:
                    st.error("用户管理页面组件未正确导入")
                    return
                render_user_management_page(current_user)
                return

            # 生产模式：进行正常的认证和权限检查
            if not current_user:
                # 显示登录提示而不是停止渲染
                st.warning("请先登录以访问用户管理功能")
                st.info("用户管理功能需要管理员权限")

                # 显示登录按钮
                if st.button("点击登录", type="primary"):
                    # 清除当前状态并重新加载登录页面
                    for key in st.session_state.keys():
                        if key.startswith('user_') or key.startswith('auth_'):
                            del st.session_state[key]
                    st.rerun()

                # 显示功能预览
                st.markdown("---")
                st.markdown("### 功能概览")
                st.markdown("- **用户列表管理** - 查看和管理所有系统用户")
                st.markdown("- **添加新用户** - 创建新的系统账户")
                st.markdown('- **权限配置** - 管理用户直接权限')
                st.markdown("- **系统统计** - 查看用户活动统计信息")
                return

            # 检查管理员权限
            if not auth_middleware.permission_manager.is_admin(current_user):
                st.error("权限不足：只有管理员可以访问用户管理功能")
                st.info("如需管理权限，请联系系统管理员")

                # 显示当前用户信息
                st.markdown("### 当前用户信息")
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

                return

            # 检查渲染函数是否可用
            if render_user_management_page is None:
                st.error("用户管理页面组件未正确导入")
                return

            # 渲染用户管理页面
            render_user_management_page(current_user)

        except Exception as e:
            st.error(f"用户管理模块初始化失败: {e}")
            raise


def render_user_management_sub_module(sub_module_name: str) -> Optional[str]:
    """
    渲染用户管理子模块

    Args:
        sub_module_name: 子模块名称

    Returns:
        渲染状态或错误信息
    """
    try:
        # 检查函数是否成功导入
        if get_auth_middleware is None:
            st.error("❌ 认证中间件未正确导入")
            return "认证中间件导入失败"

        # 获取认证中间件
        auth_middleware = get_auth_middleware()

        # 添加子模块标题
        st.markdown(f"### {sub_module_name}")

        # 检查调试模式
        debug_mode = st.session_state.get('auth.debug_mode', False)

        # 从统一状态管理器获取当前用户（避免重复认证）
        current_user = st.session_state.get("auth.current_user", None)

        # 调试模式：跳过认证和权限检查
        if debug_mode:
            st.info("调试模式：已自动授予管理员权限")
            # 在调试模式下直接渲染子模块
            if render_user_management_page is None:
                st.error("用户管理页面组件未正确导入")
                return "页面组件导入失败"

            # 根据子模块名称渲染不同内容
            if sub_module_name == "用户列表":
                render_user_management_page(current_user)
            elif sub_module_name in ("权限配置", "权限设置"):
                render_user_management_page(current_user)
            elif sub_module_name == "系统设置":
                render_user_management_page(current_user)
            else:
                st.error(f"未知的用户管理子模块: {sub_module_name}")
                st.info("可用的子模块: 用户列表, 权限配置, 系统设置")
                return f"未知子模块: {sub_module_name}"

            return "success"

        # 生产模式：进行正常的认证和权限检查
        if not current_user:
            st.warning("请先登录以访问用户管理功能")
            st.info("用户管理功能需要管理员权限")

            # 显示登录按钮
            if st.button("点击登录", key=f"login_btn_{sub_module_name}", type="primary"):
                # 清除当前状态并重新加载登录页面
                for key in st.session_state.keys():
                    if key.startswith('user_') or key.startswith('auth_'):
                        del st.session_state[key]
                st.rerun()

            return "用户未认证"

        # 检查管理员权限
        if not auth_middleware.permission_manager.is_admin(current_user):
            st.error("权限不足：只有管理员可以访问用户管理功能")
            st.info("如需管理权限，请联系系统管理员")

            # 显示当前用户信息
            with st.expander("当前用户信息", expanded=False):
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

            return "权限不足"

        # 检查渲染函数是否可用
        if render_user_management_page is None:
            st.error("❌ 用户管理页面组件未正确导入")
            return "页面组件导入失败"

        # 根据子模块名称渲染不同内容
        if sub_module_name == "用户列表":
            render_user_management_page(current_user)
        elif sub_module_name in ("权限配置", "权限设置"):
            render_user_management_page(current_user)
        elif sub_module_name == "系统设置":
            render_user_management_page(current_user)
        else:
            st.error(f"未知的用户管理子模块: {sub_module_name}")
            st.info("可用的子模块: 用户列表, 权限配置, 系统设置")
            return f"未知子模块: {sub_module_name}"

        return "success"

    except Exception as e:
        st.error(f"渲染用户管理子模块失败: {e}")
        raise
