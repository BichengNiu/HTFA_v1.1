# -*- coding: utf-8 -*-
"""
权限管理器
提供基于用户直接权限的访问控制功能
"""

from typing import List

from dashboard.auth.models import User
from dashboard.navigation_config import (
    GRANULAR_PERMISSION_MAP,
    PERMISSION_MODULE_MAP,
)


class PermissionManager:
    """权限管理器 - 基于用户直接权限体系"""
    
    def check_raw_permission(self, user: User, permission: str) -> bool:
        """
        检查用户是否具有指定的原始权限码

        Args:
            user: 用户对象
            permission: 权限码

        Returns:
            是否具有权限
        """
        if not user or not user.is_active:
            return False

        return permission in user.permissions

    def check_module_access(self, user: User, module_name: str) -> bool:
        """
        检查用户是否可以访问指定模块（模块级检查）

        Args:
            user: 用户对象
            module_name: 模块名称

        Returns:
            是否可以访问
        """
        required_permissions = PERMISSION_MODULE_MAP.get(module_name, [])

        if not required_permissions:
            return True

        return any(self.check_raw_permission(user, p) for p in required_permissions)

    def can_access_application_module(self, user: User, module_name: str) -> bool:
        """应用级主模块规则：管理员只进入用户管理，普通用户不能进入该模块。"""
        is_admin = self.is_admin(user)
        if module_name == "用户管理":
            return is_admin
        if is_admin:
            return False
        return self.check_module_access(user, module_name)

    def get_accessible_modules(self, user: User) -> List[str]:
        """
        获取用户可访问的模块列表

        Args:
            user: 用户对象

        Returns:
            可访问的模块名称列表
        """
        return [m for m in PERMISSION_MODULE_MAP.keys() if self.check_module_access(user, m)]

    def is_admin(self, user: User) -> bool:
        """
        检查用户是否为管理员

        Args:
            user: 用户对象

        Returns:
            是否为管理员
        """
        return self.check_raw_permission(user, "user_management")

    def check_granular_access(self, user: User, main_module: str,
                           sub_module: str = None, tab: str = None) -> bool:
        """
        检查用户是否具有细粒度访问权限（三级：主模块/子模块/Tab）

        Args:
            user: 用户对象
            main_module: 主模块名称
            sub_module: 子模块名称（可选）
            tab: Tab名称（可选）

        Returns:
            是否具有访问权限
        """
        if not user or not user.is_active:
            return False

        # 获取主模块配置
        main_config = GRANULAR_PERMISSION_MAP.get(main_module)
        if not main_config:
            return False

        # 如果只检查主模块
        if sub_module is None:
            return main_config["code"] in user.permissions

        # 检查子模块
        sub_modules_config = main_config.get("sub_modules")
        if not sub_modules_config:
            return False

        sub_config = sub_modules_config.get(sub_module)
        if not sub_config:
            return False

        # 如果只检查子模块
        if tab is None:
            return sub_config["code"] in user.permissions

        # 检查Tab
        tabs_config = sub_config.get("tabs")
        if not tabs_config:
            return False

        tab_code = tabs_config.get(tab)
        if not tab_code:
            return False

        return tab_code in user.permissions

    def get_accessible_submodules(self, user: User, main_module: str) -> List[str]:
        """
        获取用户在指定主模块下可访问的子模块列表

        Args:
            user: 用户对象
            main_module: 主模块名称

        Returns:
            可访问的子模块名称列表
        """
        if not user or not user.is_active:
            return []

        main_config = GRANULAR_PERMISSION_MAP.get(main_module)
        if not main_config or not main_config.get("sub_modules"):
            return []

        accessible = []
        for sub_name in main_config["sub_modules"].keys():
            if self.check_granular_access(user, main_module, sub_name):
                accessible.append(sub_name)

        return accessible
