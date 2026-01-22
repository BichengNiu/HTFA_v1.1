# -*- coding: utf-8 -*-
"""
用户信息面板组件
提供用户信息显示和登出功能
"""

import streamlit as st
from dashboard.auth.models import User
from dashboard.auth.permissions import PERMISSION_MODULE_MAP


def render_user_info_panel(user: User, on_logout_callback=None):
    """
    渲染用户信息面板

    Args:
        user: 用户对象
        on_logout_callback: 登出回调函数
    """
    if not user:
        return

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 用户信息")
        st.write(f"**用户名：** {user.username}")

        # 显示用户权限信息（转换为中文模块名称）
        if user.permissions:
            # 将权限代码转换为中文模块名称
            accessible_modules = []
            for module_name, required_perms in PERMISSION_MODULE_MAP.items():
                if any(perm in user.permissions for perm in required_perms):
                    accessible_modules.append(module_name)

            if accessible_modules:
                st.write(f"**权限：** {'、'.join(accessible_modules)}")
            else:
                st.write("**权限：** 无匹配模块")
        else:
            st.write("**权限：** 无")

        # 登出按钮
        if st.button("退出登录", key="logout_button"):
            if on_logout_callback:
                on_logout_callback()
