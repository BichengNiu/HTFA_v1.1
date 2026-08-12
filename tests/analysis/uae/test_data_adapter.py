from dashboard.analysis.uae.contracts import ProvenanceKind
from dashboard.analysis.uae.data_adapter import (
    DEFAULT_UAE_WORKBOOK,
    load_real_uae_bundle,
)
from dashboard.analysis.uae.indicator_catalog import (
    INDICATOR_SPECS,
    NOMINAL_INDUSTRY_IDS,
    REAL_INDUSTRY_IDS,
)


def test_real_default_workbook_resolves_current_growth_data():
    bundle = load_real_uae_bundle(DEFAULT_UAE_WORKBOOK)

    bundle.require_ids(
        {
            "growth.real_gdp",
            "growth.real_gdp_yoy",
            "growth.nonoil_real_gdp",
            "growth.nonoil_real_gdp_yoy",
            "growth.nonfinancial_real_gdp_yoy",
            "oil.crude_production",
            *REAL_INDUSTRY_IDS,
            *NOMINAL_INDUSTRY_IDS,
        }
    )
    assert bundle.simulated_ids == frozenset()
    assert all(
        provenance.kind is ProvenanceKind.REAL
        for provenance in bundle.provenance_by_id.values()
    )


def test_catalog_maps_uploaded_dubai_crude_indicator_exactly():
    spec = next(
        item
        for item in INDICATOR_SPECS
        if item.indicator_id == "oil.dubai_crude_price"
    )

    assert spec.aliases == ("全球: 名义商品价格: 迪拜原油",)
    assert spec.display_name == "迪拜原油价格"


def test_catalog_maps_uploaded_oil_liquids_production_exactly():
    spec = next(
        item
        for item in INDICATOR_SPECS
        if item.indicator_id == "oil.crude_production"
    )

    assert spec.aliases[0] == "阿联酋: 产量: 石油及其他液体"
    assert spec.display_name == "石油及其他液体产量"
