"""单变量数据概览在独立 Streamlit 会话间的一次性页面交接。"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from secrets import token_urlsafe
from time import monotonic

from dashboard.core.ui.utils.shared_dataset import SharedDatasetSnapshot

DEFAULT_HANDOFF_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class OverviewHandoff:
    """独立数据概览页所需的、不可变的短期快照。"""

    dataset: SharedDatasetSnapshot
    widget_state: dict[str, object]


@dataclass(frozen=True)
class _StoredHandoff:
    handoff: OverviewHandoff
    expires_at: float


class OverviewHandoffStore:
    """进程内令牌存储；令牌从不包含文件内容或控件状态。"""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_HANDOFF_TTL_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("交接令牌有效期必须为正数")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _StoredHandoff] = {}

    def create(self, handoff: OverviewHandoff) -> str:
        """保存快照并返回随机、不透明的访问令牌。"""

        if not isinstance(handoff, OverviewHandoff):
            raise TypeError("交接数据类型无效")
        self.prune()
        token = token_urlsafe(32)
        self._entries[token] = _StoredHandoff(
            handoff=deepcopy(handoff),
            expires_at=self._clock() + self._ttl_seconds,
        )
        return token

    def replace(self, previous_token: str | None, handoff: OverviewHandoff) -> str:
        """替换同一原会话的旧令牌，避免页面重跑积累过期快照。"""

        if previous_token:
            self._entries.pop(previous_token, None)
        return self.create(handoff)

    def get(self, token: str | None) -> OverviewHandoff | None:
        """返回有效快照的副本；失效令牌与不存在令牌均返回 ``None``。"""

        self.prune()
        if not isinstance(token, str) or not token:
            return None
        entry = self._entries.get(token)
        return deepcopy(entry.handoff) if entry is not None else None

    def is_valid(self, token: str | None) -> bool:
        """判断令牌是否仍存在且未过期，不复制快照内容。"""

        self.prune()
        return bool(isinstance(token, str) and token and token in self._entries)

    def prune(self) -> None:
        """删除已过期条目。"""

        now = self._clock()
        for token, entry in tuple(self._entries.items()):
            if entry.expires_at <= now:
                self._entries.pop(token, None)


overview_handoff_store = OverviewHandoffStore()


__all__ = [
    "DEFAULT_HANDOFF_TTL_SECONDS",
    "OverviewHandoff",
    "OverviewHandoffStore",
    "overview_handoff_store",
]
