"""应用共享的导航状态接口。"""

from dashboard.core.backend.navigation import (
    get_current_main_module,
    get_current_sub_module,
    reset_navigation,
    set_current_main_module,
    set_current_sub_module,
)

__version__ = "5.0.0"

__all__ = [
    "get_current_main_module",
    "get_current_sub_module",
    "reset_navigation",
    "set_current_main_module",
    "set_current_sub_module",
]
