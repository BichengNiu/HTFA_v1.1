"""导航状态公开接口。"""

from dashboard.core.backend.navigation.manager import (
    get_current_main_module,
    get_current_sub_module,
    reset_navigation,
    set_current_main_module,
    set_current_sub_module,
)

__all__ = [
    "get_current_main_module",
    "get_current_sub_module",
    "reset_navigation",
    "set_current_main_module",
    "set_current_sub_module",
]
