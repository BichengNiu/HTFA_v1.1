"""权限代码显示名工具。"""

from dashboard.navigation_config import GRANULAR_PERMISSION_MAP


class PermissionTreeBuilder:
    """权限代码显示名构建器。"""

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
