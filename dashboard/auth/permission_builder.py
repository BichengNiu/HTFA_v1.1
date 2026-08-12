# -*- coding: utf-8 -*-
"""
权限树构建工具
用于从模块配置自动构建权限树结构，提供权限管理界面使用
"""

from typing import List

from dashboard.auth.permissions import GRANULAR_PERMISSION_MAP


class PermissionTreeBuilder:
    """权限树构建器"""

    @staticmethod
    def get_all_permissions() -> List[str]:
        """
        获取所有权限代码列表

        Returns:
            所有权限代码的列表
        """
        permissions = []

        for main_name, main_config in GRANULAR_PERMISSION_MAP.items():
            # 添加主模块权限
            permissions.append(main_config["code"])

            # 添加子模块和Tab权限
            if main_config.get("sub_modules"):
                for sub_name, sub_config in main_config["sub_modules"].items():
                    permissions.append(sub_config["code"])

                    if sub_config.get("tabs"):
                        for tab_name, tab_code in sub_config["tabs"].items():
                            permissions.append(tab_code)

        return permissions

    @staticmethod
    def get_permission_display_name(permission_code: str) -> str:
        """
        根据权限代码获取显示名称

        Args:
            permission_code: 权限代码（如 "model_analysis.dfm.prep"）

        Returns:
            显示名称（如 "模型分析 - DFM 模型 - 数据准备"）
        """
        for main_name, main_config in GRANULAR_PERMISSION_MAP.items():
            if main_config["code"] == permission_code:
                return main_name

            if main_config.get("sub_modules"):
                for sub_name, sub_config in main_config["sub_modules"].items():
                    if sub_config["code"] == permission_code:
                        return f"{main_name} - {sub_name}"

                    if sub_config.get("tabs"):
                        for tab_name, tab_code in sub_config["tabs"].items():
                            if tab_code == permission_code:
                                return f"{main_name} - {sub_name} - {tab_name}"

        return permission_code
