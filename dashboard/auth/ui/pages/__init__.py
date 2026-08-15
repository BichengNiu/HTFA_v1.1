# -*- coding: utf-8 -*-
"""
Auth UI Pages 模块
认证相关的UI页面组件
"""

from dashboard.auth.ui.pages.login import LoginPage, render_login_page
from dashboard.auth.ui.pages.register import RegisterPage, render_register_page
from dashboard.auth.ui.pages.user_management import UserManagementPage, render_user_management_page

__all__ = [
    'LoginPage',
    'render_login_page',
    'RegisterPage',
    'render_register_page',
    'UserManagementPage',
    'render_user_management_page',
]
