import pytest

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    EvidenceClass,
    EvidenceItem,
    ProvenanceKind,
)
from dashboard.analysis.uae.diagnostics import (
    build_diagnostic,
    grade_confidence,
)


def evidence(kind):
    return EvidenceItem(
        label="测试证据",
        value=1.0,
        unit="%",
        evidence_class=EvidenceClass.ACCOUNTING,
        provenance_kind=kind,
        as_of="2025Q4",
    )


def test_simulation_caps_confidence_at_low():
    level, reasons = grade_confidence(
        (
            evidence(ProvenanceKind.REAL),
            evidence(ProvenanceKind.SIMULATED),
        ),
        accounting_complete=True,
    )

    assert level is ConfidenceLevel.LOW
    assert reasons == ("诊断使用了模拟数据",)


def test_real_complete_accounting_can_be_high_confidence():
    level, _ = grade_confidence(
        (evidence(ProvenanceKind.REAL),),
        accounting_complete=True,
    )

    assert level is ConfidenceLevel.HIGH


def test_non_model_diagnostic_rejects_causal_language():
    with pytest.raises(ValueError, match="不得使用确定因果措辞"):
        build_diagnostic(
            title="增长",
            result_sentence="经济增长加快。",
            accounting_sentence="制造业导致增长。",
            mechanism_sentence="",
            evidence=(evidence(ProvenanceKind.REAL),),
            limitation="无",
            accounting_complete=True,
        )


def test_diagnostic_uses_fixed_sentence_order():
    result = build_diagnostic(
        title="增长",
        result_sentence="经济增长加快。",
        accounting_sentence="制造业贡献扩大。",
        mechanism_sentence="PMI与需求改善的判断一致。",
        evidence=(evidence(ProvenanceKind.REAL),),
        limitation="相关证据不识别因果。",
        accounting_complete=True,
    )

    assert result.summary == (
        "经济增长加快。 制造业贡献扩大。 "
        "PMI与需求改善的判断一致。"
    )
