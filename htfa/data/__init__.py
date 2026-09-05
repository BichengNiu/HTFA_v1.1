"""HTFA data domain public entry points."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "DICTIONARY_SHEET_NAME": "DICTIONARY_SHEET_NAME",
    "FREQUENCIES": "FREQUENCIES",
    "IndicatorMetadata": "IndicatorMetadata",
    "EconomicWorkbookSnapshot": "EconomicWorkbookSnapshot",
    "parse_economic_workbook": "parse_economic_workbook",
}


def __getattr__(name: str) -> Any:
    """仅在调用经济工作簿入口时加载经济工作簿实现。"""
    try:
        attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(".economic_workbook", __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "DICTIONARY_SHEET_NAME",
    "FREQUENCIES",
    "IndicatorMetadata",
    "EconomicWorkbookSnapshot",
    "parse_economic_workbook",
]
