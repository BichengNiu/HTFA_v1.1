"""单变量数据概览在独立 Streamlit 会话间的一次性页面交接。"""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.core.workspace.handoff import (
    DEFAULT_HANDOFF_TTL_SECONDS,
    HandoffStore,
)
from dashboard.core.ui.utils.shared_dataset import SharedDatasetSnapshot


@dataclass(frozen=True)
class OverviewHandoff:
    """独立数据概览页所需的、不可变的短期快照。"""

    dataset: SharedDatasetSnapshot
    widget_state: dict[str, object]


class OverviewHandoffStore(HandoffStore[OverviewHandoff]):
    """数据概览专用的、带类型校验的交接令牌存储。"""

    def create(self, handoff: OverviewHandoff) -> str:
        """保存快照并返回随机、不透明的访问令牌。"""

        if not isinstance(handoff, OverviewHandoff):
            raise TypeError("交接数据类型无效")
        return super().create(handoff)


overview_handoff_store = OverviewHandoffStore()


__all__ = [
    "DEFAULT_HANDOFF_TTL_SECONDS",
    "OverviewHandoff",
    "OverviewHandoffStore",
    "overview_handoff_store",
]
