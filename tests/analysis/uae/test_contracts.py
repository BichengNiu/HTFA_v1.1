import pandas as pd
import pytest

from htfa.monitoring.uae.contracts import (
    DataProvenance,
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
