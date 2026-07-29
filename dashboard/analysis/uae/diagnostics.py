"""确定性宏观诊断叙事和置信度规则。"""

from __future__ import annotations

from collections.abc import Iterable

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    DiagnosticResult,
    EvidenceItem,
    ProvenanceKind,
)


CAUSAL_WORDS = ("导致", "造成", "决定")


def grade_confidence(
    evidence: Iterable[EvidenceItem],
    *,
    accounting_complete: bool,
    evidence_conflict: bool = False,
) -> tuple[ConfidenceLevel, tuple[str, ...]]:
    """按数据来源和核算覆盖确定置信度。"""

    items = tuple(evidence)
    reasons: list[str] = []
    if any(
        item.provenance_kind is ProvenanceKind.SIMULATED
        for item in items
    ):
        reasons.append("诊断使用了模拟数据")
        return ConfidenceLevel.LOW, tuple(reasons)

    level = ConfidenceLevel.HIGH
    if not accounting_complete:
        level = ConfidenceLevel.MEDIUM
        reasons.append("核算分项存在未覆盖残差")
    if evidence_conflict:
        level = (
            ConfidenceLevel.LOW
            if level is ConfidenceLevel.MEDIUM
            else ConfidenceLevel.MEDIUM
        )
        reasons.append("机制证据方向不一致")
    if not reasons:
        reasons.append("核算覆盖完整且证据均为真实数据")
    return level, tuple(reasons)


def build_diagnostic(
    *,
    title: str,
    result_sentence: str,
    accounting_sentence: str,
    mechanism_sentence: str,
    evidence: tuple[EvidenceItem, ...],
    limitation: str,
    accounting_complete: bool,
    evidence_conflict: bool = False,
) -> DiagnosticResult:
    """按固定句序生成可审计诊断。"""

    summary = " ".join(
        sentence.strip()
        for sentence in (
            result_sentence,
            accounting_sentence,
            mechanism_sentence,
        )
        if sentence.strip()
    )
    if any(word in summary for word in CAUSAL_WORDS):
        raise ValueError("非模型诊断不得使用确定因果措辞")
    confidence, reasons = grade_confidence(
        evidence,
        accounting_complete=accounting_complete,
        evidence_conflict=evidence_conflict,
    )
    return DiagnosticResult(
        title=title,
        summary=summary,
        confidence=confidence,
        confidence_reasons=reasons,
        evidence=evidence,
        limitation=limitation,
    )

