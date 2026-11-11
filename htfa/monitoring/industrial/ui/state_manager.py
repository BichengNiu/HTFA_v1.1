"""工业分析共享状态。"""

from htfa.monitoring.industrial.contracts.constants import STATE_NAMESPACE_INDUSTRIAL
from htfa.ui_shared.session_state import NamespacedStateManager

industrial_state = NamespacedStateManager(STATE_NAMESPACE_INDUSTRIAL)

__all__ = ["industrial_state"]
