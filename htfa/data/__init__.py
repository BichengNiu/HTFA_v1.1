"""HTFA data domain public entry points."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "DICTIONARY_SHEET_NAME": (".economic_workbook", "DICTIONARY_SHEET_NAME"),
    "FREQUENCIES": (".economic_workbook", "FREQUENCIES"),
    "IndicatorMetadata": (".economic_workbook", "IndicatorMetadata"),
    "EconomicWorkbookReader": (".economic_workbook", "EconomicWorkbookReader"),
    "EconomicWorkbookSnapshot": (".economic_workbook", "EconomicWorkbookSnapshot"),
    "TabularInputSource": (".tabular", "TabularInputSource"),
}


def __getattr__(name: str) -> Any:
    """按需加载数据领域的公共协议，避免顶层导入 UI 依赖。"""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "DICTIONARY_SHEET_NAME",
    "FREQUENCIES",
    "IndicatorMetadata",
    "EconomicWorkbookSnapshot",
    "EconomicWorkbookReader",
    "TabularInputSource",
]
