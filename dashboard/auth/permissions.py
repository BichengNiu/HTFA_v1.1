# -*- coding: utf-8 -*-
"""
权限管理器
提供基于用户直接权限的访问控制功能
"""

from typing import List, Dict, Optional, Set
import logging

from dashboard.auth.database import AuthDatabase
from dashboard.auth.models import User


# 权限模块映射（旧版，保留兼容性）
PERMISSION_MODULE_MAP = {
    "数据预览": ["data_preview"],
    "监测分析": ["monitoring_analysis"],
    "模型分析": ["model_analysis"],
    "数据探索": ["data_exploration"],
    "用户管理": ["user_management"]
}

# 细粒度权限映射（三级结构：主模块 -> 子模块 -> Tab）
GRANULAR_PERMISSION_MAP = {
    "数据预览": {
        "code": "data_preview",
        "sub_modules": {
            "工业": {
                "code": "data_preview.industrial",
                "tabs": None
            }
        }
    },
    "监测分析": {
        "code": "monitoring_analysis",
        "sub_modules": {
            "工业": {
                "code": "monitoring_analysis.industrial",
                "tabs": {
                    "工业增加值分析": "monitoring_analysis.industrial.added_value",
                    "工业企业利润分析": "monitoring_analysis.industrial.profit",
                    "工业企业经营效率分析": "monitoring_analysis.industrial.efficiency"
                }
            }
        }
    },
    "模型分析": {
        "code": "model_analysis",
        "sub_modules": {
            "DFM 模型": {
                "code": "model_analysis.dfm",
                "tabs": {
                    "数据准备": "model_analysis.dfm.prep",
                    "模型训练": "model_analysis.dfm.train",
                    "模型分析": "model_analysis.dfm.analysis",
                    "影响分解": "model_analysis.dfm.news"
                }
            }
        }
    },
    "数据探索": {
        "code": "data_exploration",
        "sub_modules": {
            "时序性质": {
                "code": "data_exploration.univariate",
                "tabs": {
                    "平稳性分析": "data_exploration.univariate.stationarity"
                }
            },
            "时序关系": {
                "code": "data_exploration.bivariate",
                "tabs": {
                    "相关分析": "data_exploration.bivariate.correlation",
                    "领先滞后分析": "data_exploration.bivariate.lead_lag"
                }
            }
        }
    },
    "用户管理": {
        "code": "user_management",
        "sub_modules": None
    }
}


class PermissionManager:
    """权限管理器 - 基于用户直接权限体系"""
    
    def __init__(self, db_path: str = None):
        """初始化权限管理器"""
        self.db = AuthDatabase(db_path)
        self.logger = logging.getLogger(__name__)
    
    def has_permission(self, user: User, permission: str) -> bool:
        """
        检查用户是否具有指定权限

        Args:
            user: 用户对象
            permission: 权限名称

        Returns:
            是否具有权限
        """
        if not user or not user.is_active:
            return False

        return permission in user.permissions
    
    def has_module_access(self, user: User, module_name: str) -> bool:
        """
        检查用户是否可以访问指定模块

        Args:
            user: 用户对象
            module_name: 模块名称

        Returns:
            是否可以访问
        """
        required_permissions = PERMISSION_MODULE_MAP.get(module_name, [])

        if not required_permissions:
            return True

        return any(self.has_permission(user, p) for p in required_permissions)
    
    def get_accessible_modules(self, user: User) -> List[str]:
        """
        获取用户可访问的模块列表

        Args:
            user: 用户对象

        Returns:
            可访问的模块名称列表
        """
        return [m for m in PERMISSION_MODULE_MAP.keys() if self.has_module_access(user, m)]

    def is_admin(self, user: User) -> bool:
        """
        检查用户是否为管理员

        Args:
            user: 用户对象

        Returns:
            是否为管理员
        """
        return self.has_permission(user, "user_management")

    def filter_accessible_modules(self, user: User, modules: Dict) -> Dict:
        """
        过滤用户可访问的模块配置

        Args:
            user: 用户对象
            modules: 原始模块配置

        Returns:
            过滤后的模块配置
        """
        return {
            main_module: sub_modules
            for main_module, sub_modules in modules.items()
            if self.has_module_access(user, main_module)
        }

    def has_granular_access(self, user: User, main_module: str,
                           sub_module: str = None, tab: str = None) -> bool:
        """
        检查用户是否具有细粒度访问权限（无自动继承）

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
            if self.has_granular_access(user, main_module, sub_name):
                accessible.append(sub_name)

        return accessible

    def get_accessible_tabs(self, user: User, main_module: str, sub_module: str) -> List[str]:
        """
        获取用户在指定子模块下可访问的Tab列表

        Args:
            user: 用户对象
            main_module: 主模块名称
            sub_module: 子模块名称

        Returns:
            可访问的Tab名称列表
        """
        if not user or not user.is_active:
            return []

        main_config = GRANULAR_PERMISSION_MAP.get(main_module)
        if not main_config or not main_config.get("sub_modules"):
            return []

        sub_config = main_config["sub_modules"].get(sub_module)
        if not sub_config or not sub_config.get("tabs"):
            return []

        accessible = []
        for tab_name in sub_config["tabs"].keys():
            if self.has_granular_access(user, main_module, sub_module, tab_name):
                accessible.append(tab_name)

        return accessible

    def get_user_permissions_tree(self, user: User) -> Dict:
        """
        获取用户权限的树形结构（用于UI显示）

        Args:
            user: 用户对象

        Returns:
            权限树字典
        """
        if not user or not user.is_active:
            return {}

        tree = {}
        for main_name, main_config in GRANULAR_PERMISSION_MAP.items():
            main_code = main_config["code"]
            has_main = main_code in user.permissions

            sub_tree = {}
            if main_config.get("sub_modules"):
                for sub_name, sub_config in main_config["sub_modules"].items():
                    sub_code = sub_config["code"]
                    has_sub = sub_code in user.permissions

                    tab_tree = {}
                    if sub_config.get("tabs"):
                        for tab_name, tab_code in sub_config["tabs"].items():
                            tab_tree[tab_name] = tab_code in user.permissions

                    sub_tree[sub_name] = {
                        "has_access": has_sub,
                        "tabs": tab_tree
                    }

            tree[main_name] = {
                "has_access": has_main,
                "sub_modules": sub_tree
            }

        return tree
