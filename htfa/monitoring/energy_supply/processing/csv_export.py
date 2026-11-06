"""Shared safe CSV serialization for every application export."""
from __future__ import annotations

import csv
import io


def safe_csv_value(value):
    """Make untrusted text inert when opened by spreadsheet applications."""
    if isinstance(value, str) and value.lstrip().lstrip("\ufeff").startswith(
            ("=", "+", "-", "@")):
        return "'" + value
    return value


def csv_bytes(rows: list[dict], fields: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows({
        key: safe_csv_value(row.get(key)) for key in fields
    } for row in rows)
    return buffer.getvalue().encode("utf-8-sig")
