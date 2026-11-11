"""HTFA 会话工作区的公共接口，按需加载会话能力。"""
from importlib import import_module

_EXPORTS = {
    "AssetUpdate": ".workspace", "DatasetSnapshot": ".workspace",
    "DatasetProtocol": ".workspace", "FileAsset": ".workspace",
    "NamedBytesIO": ".workspace", "SessionWorkspace": ".workspace",
    "DEFAULT_HANDOFF_TTL_SECONDS": ".handoff", "HandoffStore": ".handoff",
    "artifact_is_current": ".signatures", "artifact_signature": ".signatures",
    "stable_signature": ".signatures",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    """加载请求的工作区接口，不初始化无关会话服务。"""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
