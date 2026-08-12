"""少量跨页面共享的 UI 常量。"""

from enum import Enum

from dashboard.navigation_config import MAIN_MODULES, SUB_MODULES


class NavigationLevel(Enum):
    """导航层级。"""

    MAIN_MODULE = "main_module"
    SUB_MODULE = "sub_module"
    FUNCTION = "function"


class UIConstants:
    """保留现有页面使用的常量访问方式。"""

    EXPLORATION_ANALYSIS_MODULES = [
        "stationarity",
        "time_lag_corr",
        "lead_lag",
    ]
    MAIN_MODULES = MAIN_MODULES
    SUB_MODULES = SUB_MODULES


__all__ = ["NavigationLevel", "UIConstants"]
