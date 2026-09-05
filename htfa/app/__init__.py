"""应用共享的导航状态接口。"""

from .navigation.manager import (
    get_current_main_module,
    get_current_sub_module,
    set_current_main_module,
    set_current_sub_module,
)

__all__ = [
    "get_current_main_module",
    "get_current_sub_module",
    "set_current_main_module",
    "set_current_sub_module",
]
