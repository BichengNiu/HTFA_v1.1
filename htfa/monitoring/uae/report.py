"""阿联酋高频监测报告的主题组合边界。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from htfa.monitoring.uae.database import PublishedUAEData
from htfa.monitoring.uae.government_finance.renderer import (
    render_government_finance_section,
)
from htfa.monitoring.uae.oil.renderer import render_oil_fiscal_panel
from htfa.monitoring.uae.real_estate.renderer import render_real_estate_section
from htfa.monitoring.uae.transport.renderer import render_transport_section
from htfa.monitoring.uae.supplemental_renderer import render_prices_section


TopicStatus = Literal["ok", "empty", "failed"]
TopicRenderer = Callable[[Any, PublishedUAEData], Mapping[str, Any]]


@dataclass(frozen=True)
class TopicResult:
    """一次监测主题渲染的明确结果。"""

    status: TopicStatus
    payload: Mapping[str, Any] | None = None
    error: str | None = None


TOPIC_RENDERERS: tuple[tuple[str, str, TopicRenderer], ...] = (
    ("oil", "石油生产与收入", render_oil_fiscal_panel),
    ("government_finance", "政府金融", render_government_finance_section),
    ("real_estate", "房地产", render_real_estate_section),
    ("transport", "交通物流", render_transport_section),
    ("prices", "物价", render_prices_section),
)


def render_high_frequency_topics(
    st_obj: Any,
    source: PublishedUAEData,
) -> dict[str, TopicResult]:
    """独立渲染高频主题；单主题失败不阻断其他主题。"""

    results: dict[str, TopicResult] = {}
    for topic, label, renderer in TOPIC_RENDERERS:
        try:
            rendered = renderer(st_obj, source)
            status = _status_from_payload(rendered)
        except Exception as exc:  # noqa: BLE001 - 主题隔离边界
            message = f"{label}主题渲染失败：{exc}"
            st_obj.error(message)
            results[topic] = TopicResult(
                status="failed",
                error=str(exc),
            )
            continue

        results[topic] = TopicResult(
            status=status,
            payload=dict(rendered),
            error=(
                str(rendered.get("message"))
                if status == "failed" and rendered.get("message")
                else None
            ),
        )
    return results


def _status_from_payload(payload: Mapping[str, Any]) -> TopicStatus:
    status = payload.get("status")
    if status == "success":
        return "ok"
    if status == "no_data":
        return "empty"
    if status == "error":
        return "failed"
    raise ValueError(f"主题返回了无效状态：{status!r}")


__all__ = ["TOPIC_RENDERERS", "TopicResult", "render_high_frequency_topics"]
