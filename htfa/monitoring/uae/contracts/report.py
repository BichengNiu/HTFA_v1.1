from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Literal

TopicStatus = Literal["ok", "empty", "failed"]


@dataclass(frozen=True)
class TopicResult:
    """一次监测主题渲染的明确结果。"""

    status: TopicStatus
    payload: Mapping[str, Any] | None = None
    error: str | None = None
