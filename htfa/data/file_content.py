"""文件内容级基础能力。"""

from __future__ import annotations

from hashlib import sha256


def file_fingerprint(content: bytes) -> str:
    """返回只由文件内容决定的稳定 SHA-256 指纹。"""
    if not isinstance(content, bytes):
        raise TypeError("文件内容必须是 bytes")
    return sha256(content).hexdigest()


__all__ = ["file_fingerprint"]
