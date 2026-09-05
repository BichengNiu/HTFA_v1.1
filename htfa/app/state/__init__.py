"""应用会话状态与共享数据集适配器。"""

from . import shared_dataset
from .session_state import (
    NamespacedStateManager,
    clear_economic_workbook_state,
    clear_state_by_prefix,
    get_economic_workbook_state,
    set_economic_workbook_state,
)

__all__ = [
    "NamespacedStateManager",
    "clear_economic_workbook_state",
    "clear_state_by_prefix",
    "get_economic_workbook_state",
    "set_economic_workbook_state",
    "shared_dataset",
]
