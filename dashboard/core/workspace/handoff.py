"""跨独立页面会话的短期、不透明交接令牌存储。"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from secrets import token_urlsafe
from time import monotonic
from typing import Generic, TypeVar


HandoffT = TypeVar("HandoffT")
DEFAULT_HANDOFF_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class _StoredHandoff(Generic[HandoffT]):
    handoff: HandoffT
    expires_at: float


class HandoffStore(Generic[HandoffT]):
    """进程内令牌存储；令牌不包含交接数据本身。"""

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
        self._entries: dict[str, _StoredHandoff[HandoffT]] = {}

    def create(self, handoff: HandoffT) -> str:
        """保存快照并返回随机、不透明的访问令牌。"""

        self.prune()
        token = token_urlsafe(32)
        self._entries[token] = _StoredHandoff(
            handoff=deepcopy(handoff),
            expires_at=self._clock() + self._ttl_seconds,
        )
        return token

    def replace(self, previous_token: str | None, handoff: HandoffT) -> str:
        """替换同一原会话的旧令牌，避免页面重跑积累快照。"""

        if previous_token:
            self._entries.pop(previous_token, None)
        return self.create(handoff)

    def get(self, token: str | None) -> HandoffT | None:
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


__all__ = ["DEFAULT_HANDOFF_TTL_SECONDS", "HandoffStore"]
