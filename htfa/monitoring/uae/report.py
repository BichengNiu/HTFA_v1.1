"""阿联酋高频监测报告的主题组合边界。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from htfa.monitoring.uae.government_finance import (
    render_government_finance_section,
)
from htfa.monitoring.uae.oil import render_oil_fiscal_panel
from htfa.monitoring.uae.real_estate import render_real_estate_section
from htfa.monitoring.uae.transport import render_transport_section


TopicStatus = Literal["ok", "empty", "failed"]
TopicRenderer = Callable[[Any, tuple[bytes, str]], Mapping[str, Any]]


@dataclass(frozen=True)
class TopicResult:
    """一次监测主题渲染的明确结果。"""

    topic: str
    status: TopicStatus
    payload: Mapping[str, Any] | None = None
    error: str | None = None


def _render_government_finance(
    st_obj: Any,
    payload: tuple[bytes, str],
) -> Mapping[str, Any]:
    return render_government_finance_section(st_obj, *payload)


def _render_real_estate(
    st_obj: Any,
    payload: tuple[bytes, str],
) -> Mapping[str, Any]:
    return render_real_estate_section(st_obj, *payload)


def _render_transport(
    st_obj: Any,
    payload: tuple[bytes, str],
) -> Mapping[str, Any]:
    return render_transport_section(st_obj, *payload)


TOPIC_RENDERERS: tuple[tuple[str, str, TopicRenderer], ...] = (
    ("oil", "石油生产与收入", render_oil_fiscal_panel),
    ("government_finance", "政府金融", _render_government_finance),
    ("real_estate", "房地产", _render_real_estate),
    ("transport", "交通物流", _render_transport),
)


def render_high_frequency_topics(
    st_obj: Any,
    payload: tuple[bytes, str],
) -> dict[str, TopicResult]:
    """独立渲染高频主题；单主题失败不阻断其他主题。"""

    results: dict[str, TopicResult] = {}
    for topic, label, renderer in TOPIC_RENDERERS:
        try:
            rendered = renderer(st_obj, payload)
        except Exception as exc:  # noqa: BLE001 - 主题隔离边界
            message = f"{label}主题渲染失败：{exc}"
            st_obj.error(message)
            results[topic] = TopicResult(
                topic=topic,
                status="failed",
                error=str(exc),
            )
            continue

        status = _status_from_payload(rendered)
        results[topic] = TopicResult(
            topic=topic,
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
    status = payload.get("status", "success")
    if status in {"success", "ok"}:
        return "ok"
    if status in {"no_data", "empty"}:
        return "empty"
    return "failed"


__all__ = ["TOPIC_RENDERERS", "TopicResult", "render_high_frequency_topics"]
