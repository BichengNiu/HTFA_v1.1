import pytest

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    ProvenanceKind,
)
from dashboard.analysis.uae.data_adapter import load_runtime_uae_bundle
from dashboard.analysis.uae.services import (
    build_growth_panel,
    build_monitoring_dashboard,
)


@pytest.fixture(scope="module")
def dashboard_result():
    return build_monitoring_dashboard()


def test_dashboard_builds_all_detailed_macro_panels(dashboard_result):
    assert tuple(dashboard_result.panels) == (
        "growth",
        "inflation",
        "labor",
        "fiscal_external",
        "monetary",
    )


def test_all_panels_expose_result_accounting_mechanism_and_limits(
    dashboard_result,
):
    for panel in dashboard_result.panels.values():
        assert panel.metrics
        assert panel.series_groups
        assert panel.headline.summary
        assert panel.headline.evidence
        assert panel.headline.limitation
        assert panel.methodology_notes


def test_simulation_caps_every_mixed_or_simulated_headline_at_low(
    dashboard_result,
):
    for panel in dashboard_result.panels.values():
        assert panel.headline.uses_simulated_data
        assert panel.headline.confidence is ConfidenceLevel.LOW
        assert any(
            "模拟数据" in reason
            for reason in panel.headline.confidence_reasons
        )


def test_growth_uses_real_results_and_explicit_residual():
    bundle = load_runtime_uae_bundle()
    panel = build_growth_panel(bundle)

    assert panel.provenance["growth.real_gdp"].kind is ProvenanceKind.REAL
    assert panel.provenance["oil.brent_price"].kind is ProvenanceKind.SIMULATED
    assert "其他行业、税收与残差" in (
        panel.decomposition_tables["行业增长贡献"].columns
    )


def test_growth_industry_contributions_reconcile_to_total():
    bundle = load_runtime_uae_bundle()
    panel = build_growth_panel(bundle)
    contributions = panel.decomposition_tables["行业增长贡献"]
    total = panel.series_groups["增长趋势"]["实际GDP同比"]

    latest = contributions.dropna(how="all").index[-1]
    assert contributions.loc[latest].sum() == pytest.approx(total.loc[latest])


def test_fiscal_and_external_decompositions_remain_visible(
    dashboard_result,
):
    panel = dashboard_result.require_panel("fiscal_external")

    assert set(panel.decomposition_tables) == {
        "一般政府财政拆解",
        "经常账户拆解",
    }


def test_deterministic_narratives_avoid_causal_claims(dashboard_result):
    banned = ("导致", "造成", "决定")

    for panel in dashboard_result.panels.values():
        assert not any(word in panel.headline.summary for word in banned)
