from __future__ import annotations
from collections.abc import Iterable
from typing import Any


def render_metric_cards(
    st_obj: Any, cards: Iterable[tuple[str, str | None, str | None, str]]
) -> None:
    """将 (label, value, delta, help) 卡片左对齐排列，空间不足时自动换行。

    主值或 delta 为 None 时展示「—」（同石油活跃钻机数缺失时的降级）。
    """
    with st_obj.container(horizontal=True, horizontal_alignment="left"):
        for label, value, delta, help_text in cards:
            st_obj.metric(
                label,
                "—" if value is None else value,
                delta=delta,
                delta_color="off",
                help=help_text,
                width=300,
            )
