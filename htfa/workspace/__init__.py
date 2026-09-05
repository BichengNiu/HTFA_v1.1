"""HTFA 会话工作区的公共接口。"""

from .handoff import DEFAULT_HANDOFF_TTL_SECONDS, HandoffStore
from .signatures import artifact_is_current, artifact_signature, stable_signature
from .workspace import (
    AssetUpdate,
    DatasetSnapshot,
    DatasetProtocol,
    FileAsset,
    NamedBytesIO,
    SessionWorkspace,
)

__all__ = [
    "AssetUpdate",
    "DatasetSnapshot",
    "DatasetProtocol",
    "DEFAULT_HANDOFF_TTL_SECONDS",
    "FileAsset",
    "HandoffStore",
    "NamedBytesIO",
    "SessionWorkspace",
    "artifact_is_current",
    "artifact_signature",
    "stable_signature",
]
