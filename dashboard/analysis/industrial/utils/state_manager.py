"""工业分析共享状态。"""

from dashboard.core.ui.utils.state_helpers import NamespacedStateManager

industrial_state = NamespacedStateManager("industrial.analysis")

__all__ = ["industrial_state"]
