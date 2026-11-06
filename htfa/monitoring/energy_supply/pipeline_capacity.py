"""Exact volume-unit conversion; mass capacity needs a density, not an energy factor."""
from decimal import Decimal, InvalidOperation
import hashlib
import json


def review_digest(review):
    payload = json.dumps(review, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def million_bpd(value, unit):
    if value in (None, "", "--") or unit != "bpd":
        return None
    try:
        amount = Decimal(str(value).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("管线运力数值无效") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("管线运力必须为非负有限值")
    return format((amount / Decimal(1000000)).normalize(), "f")


def display(value, *, approximate=False):
    if value is None:
        return "未披露"
    return ("约 " if approximate else "") + str(value) + " 百万桶/日"
