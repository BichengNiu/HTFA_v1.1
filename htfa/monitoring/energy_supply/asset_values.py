"""Format published asset values while keeping numeric amounts typed."""

from __future__ import annotations

from typing import Any


def _format_amount(amount) -> str:
    text = format(amount, ",f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def display_value(asset: dict[str, Any]) -> str:
    """Format an asset's numeric amount, qualifier, and display unit."""
    value = asset.get("value")
    numeric = asset.get("value_numeric")
    unit = asset.get("unit")
    if value is None:
        return "未披露"
    if numeric is not None:
        qualifier = str(asset.get("value_qualifier") or "")

        prefix = f"{qualifier} " if qualifier else ""
        if unit and str(unit).startswith("千桶/日"):
            amount = numeric / 10
            suffix = str(unit)[len("千桶/日") :]
            return f"{prefix}{_format_amount(amount)} 万桶/日{suffix}"
        label = f"{prefix}{_format_amount(numeric)}"
        return f"{label} {unit}" if unit else label
    if unit and str(unit).startswith("千桶/日"):
        try:
            ten_thousand_barrels = float(str(value).replace(",", "")) / 10
            formatted = f"{ten_thousand_barrels:,.2f}".rstrip("0").rstrip(".")
            suffix = str(unit)[len("千桶/日") :]
            return f"{formatted} 万桶/日{suffix}"
        except ValueError:
            pass
    return f"{value} {unit}" if unit else str(value)
