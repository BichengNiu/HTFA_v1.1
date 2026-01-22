# -*- coding: utf-8 -*-
"""
权限树构建工具
用于从模块配置自动构建权限树结构，提供权限管理界面使用
"""

from typing import Dict, List, Tuple
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
    def get_permission_tree_structure() -> Dict:
        """
        获取权限树形结构（用于UI渲染）

        Returns:
            树形结构字典，包含所有层级的名称和权限代码
        """
        tree = {}

        for main_name, main_config in GRANULAR_PERMISSION_MAP.items():
            main_node = {
                "display_name": main_name,
                "code": main_config["code"],
                "sub_modules": {}
            }

            if main_config.get("sub_modules"):
                for sub_name, sub_config in main_config["sub_modules"].items():
                    sub_node = {
                        "display_name": sub_name,
                        "code": sub_config["code"],
                        "tabs": {}
                    }

                    if sub_config.get("tabs"):
                        for tab_name, tab_code in sub_config["tabs"].items():
                            sub_node["tabs"][tab_name] = {
                                "display_name": tab_name,
                                "code": tab_code
                            }

                    main_node["sub_modules"][sub_name] = sub_node

            tree[main_name] = main_node

        return tree

    @staticmethod
    def validate_permissions(permissions: List[str]) -> Tuple[bool, List[str]]:
        """
        验证权限代码列表的有效性

        Args:
            permissions: 待验证的权限代码列表

        Returns:
            (是否全部有效, 无效的权限代码列表)
        """
        all_valid_permissions = set(PermissionTreeBuilder.get_all_permissions())
        invalid = [p for p in permissions if p not in all_valid_permissions]
        return len(invalid) == 0, invalid

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

    @staticmethod
    def get_permissions_summary(permissions: List[str]) -> Dict[str, List[str]]:
        """
        对权限列表进行分组汇总

        Args:
            permissions: 权限代码列表

        Returns:
            按模块分组的权限摘要
        """
        summary = {}

        for perm in permissions:
            parts = perm.split(".")
            main_key = parts[0]

            if main_key not in summary:
                summary[main_key] = []

            summary[main_key].append(perm)

        return summary
