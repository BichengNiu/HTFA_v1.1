# -*- coding: utf-8 -*-
"""
Auth UI 模块
认证相关的UI组件和页面
"""

# 导出中间件
from dashboard.auth.ui.middleware import (
    AuthMiddleware,
    get_auth_middleware
)

# 导出页面渲染函数
from dashboard.auth.ui.pages.login import render_login_page
from dashboard.auth.ui.pages.register import render_register_page
from dashboard.auth.ui.pages.user_management import render_user_management_page
from dashboard.auth.ui.pages.user_management_module import (
    UserManagementWelcomePage,
    render_user_management_sub_module
)

__all__ = [
    # 中间件
    'AuthMiddleware',
    'get_auth_middleware',

    # 页面
    'render_login_page',
    'render_register_page',
    'render_user_management_page',
    'UserManagementWelcomePage',
    'render_user_management_sub_module',
]
