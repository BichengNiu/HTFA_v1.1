"""工业分析共享状态。"""

from dashboard.analysis.industrial.constants import STATE_NAMESPACE_INDUSTRIAL
from dashboard.core.ui.utils.state_helpers import NamespacedStateManager

industrial_state = NamespacedStateManager(STATE_NAMESPACE_INDUSTRIAL)

__all__ = ["industrial_state"]
