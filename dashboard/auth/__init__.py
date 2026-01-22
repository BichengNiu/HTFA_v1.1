# -*- coding: utf-8 -*-
"""
认证模块
提供用户认证、权限管理等功能
"""

from dashboard.auth.authentication import AuthManager
from dashboard.auth.permissions import PermissionManager
from dashboard.auth.models import User, UserSession
from dashboard.auth.config import AuthConfig

__all__ = [
    'AuthManager',
    'PermissionManager',
    'User',
    'UserSession',
    'AuthConfig'
]
