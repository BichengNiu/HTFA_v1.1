import pandas as pd
import pytest

from htfa.monitoring.uae.contracts import (
    ConfidenceLevel,
    DataProvenance,
    DiagnosticResult,
    EvidenceClass,
    EvidenceItem,
    ProvenanceKind,
    UAEDataBundle,
)


def _provenance(indicator_id, kind=ProvenanceKind.REAL):
    return DataProvenance(
        indicator_id=indicator_id,
        display_name="测试指标",
        kind=kind,
        source="测试来源",
        frequency="quarterly",
        unit="指数",
        coverage="全国",
        as_of="2025Q4",
    )


def test_bundle_returns_a_copy_of_a_known_series():
    indicator_id = "growth.real_gdp"
    source = pd.Series(
        [100.0, 105.0],
        index=pd.period_range("2025Q1", periods=2, freq="Q"),
        name="实际GDP",
    )
    bundle = UAEDataBundle(
        series_by_id={indicator_id: source},
        provenance_by_id={indicator_id: _provenance(indicator_id)},
    )

    result = bundle.require_series(indicator_id)
    result.iloc[0] = -1.0

    assert source.iloc[0] == 100.0


def test_bundle_reports_missing_semantic_ids_together():
    bundle = UAEDataBundle(series_by_id={}, provenance_by_id={})

    with pytest.raises(
        ValueError,
        match="growth.nonoil_real_gdp, growth.real_gdp",
    ):
        bundle.require_ids(
            {"growth.real_gdp", "growth.nonoil_real_gdp"}
        )


def test_bundle_exposes_simulated_provenance():
    indicator_id = "inflation.cpi_all"
    bundle = UAEDataBundle(
        series_by_id={
            indicator_id: pd.Series(
                [100.0],
                index=pd.period_range("2025-01", periods=1, freq="M"),
            )
        },
        provenance_by_id={
            indicator_id: _provenance(
                indicator_id,
                ProvenanceKind.SIMULATED,
            )
        },
    )

    assert bundle.is_simulated(indicator_id)


def test_diagnostic_detects_simulated_evidence():
    result = DiagnosticResult(
        title="通胀",
        summary="通胀回落。",
        confidence=ConfidenceLevel.LOW,
        confidence_reasons=("使用模拟数据",),
        evidence=(
            EvidenceItem(
                label="总体CPI",
                value=2.0,
                unit="%",
                evidence_class=EvidenceClass.ACCOUNTING,
                provenance_kind=ProvenanceKind.SIMULATED,
                as_of="2025-12",
            ),
        ),
        limitation="模拟数据仅用于页面开发。",
    )

    assert result.uses_simulated_data
