"""文件内容级基础能力。"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any


def read_file_bytes(file_input: Any) -> bytes:
    """读取文件输入的完整 bytes，并恢复可定位文件的原始游标。"""

    if isinstance(file_input, bytes):
        return file_input
    if isinstance(file_input, (str, Path)):
        return Path(file_input).read_bytes()
    if hasattr(file_input, "getvalue"):
        content = file_input.getvalue()
    elif hasattr(file_input, "read"):
        position = file_input.tell() if hasattr(file_input, "tell") else None
        content = file_input.read()
        if position is not None and hasattr(file_input, "seek"):
            file_input.seek(position)
    else:
        raise TypeError("文件输入必须是 bytes、路径或可读取的二进制文件对象")
    if not isinstance(content, bytes):
        raise TypeError("文件输入必须提供 bytes 内容")
    return content


def file_fingerprint(content: bytes) -> str:
    """返回只由文件内容决定的稳定 SHA-256 指纹。"""
    if not isinstance(content, bytes):
        raise TypeError("文件内容必须是 bytes")
    return sha256(content).hexdigest()


__all__ = ["file_fingerprint", "read_file_bytes"]
