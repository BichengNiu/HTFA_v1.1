"""用于会话派生结果的稳定签名。"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from hashlib import sha256
from typing import Any


def stable_signature(value: Any) -> str:
    """返回只依赖受支持值内容的 SHA-256 签名。

    支持 ``None``、布尔值、数值、字符串、日期时间、列表/元组和字符串键映射。
    未受支持的对象会显式报错，以避免对象字符串表示造成不稳定的缓存键。
    """

    encoded = json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def artifact_signature(
    *,
    data_fingerprint: str,
    parameters: Any,
    version: str,
) -> str:
    """返回由数据、参数和算法版本共同决定的结果签名。"""

    return stable_signature(
        {
            "data_fingerprint": data_fingerprint,
            "parameters": parameters,
            "version": version,
        }
    )


def artifact_is_current(stored: str | None, current: str) -> bool:
    """判断已保存结果是否仍匹配当前签名。"""

    return bool(stored) and stored == current


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise TypeError("签名不支持 NaN 或无穷数值")
        return value
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("签名映射的键必须是字符串")
        return {key: _normalize(item) for key, item in value.items()}
    raise TypeError(f"签名不支持 {type(value).__name__} 对象")


__all__ = ["artifact_is_current", "artifact_signature", "stable_signature"]
