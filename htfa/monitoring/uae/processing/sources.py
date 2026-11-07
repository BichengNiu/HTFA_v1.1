from __future__ import annotations
import re
from htfa.monitoring.uae.contracts.sources import SOURCE_DISPLAY_NAMES


def translate_source_text(source_text: str) -> str:
    """把来源字符串中的数据源名称统一转换为中文展示文本。"""
    names = [
        _remove_parenthetical_text(SOURCE_DISPLAY_NAMES.get(part.strip(), part.strip()))
        for part in re.split("[、；]", source_text)
        if part.strip()
    ]
    return "、".join(names)


def _remove_parenthetical_text(value: str) -> str:
    """删除来源展示名中的中英文括号及括号内说明。"""
    cleaned = value
    while True:
        without_parenthetical = re.sub("\\s*(?:（[^（）]*）|\\([^()]*\\))", "", cleaned)
        if without_parenthetical == cleaned:
            return cleaned.strip()
        cleaned = without_parenthetical


def source_note(source_text: str) -> str:
    """把原始来源字符串转换为中文图注。"""
    return f"数据来源：{translate_source_text(source_text)}"
