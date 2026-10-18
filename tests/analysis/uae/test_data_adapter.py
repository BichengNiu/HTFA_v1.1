from htfa.monitoring.uae.indicator_catalog import (
    INDICATOR_SPECS,
)


def test_catalog_maps_uploaded_oil_liquids_production_exactly():
    spec = next(
        item
        for item in INDICATOR_SPECS
        if item.indicator_id == "oil.crude_production"
    )

    assert spec.indicator_name == "阿联酋: 产量: 石油及其他液体"
    assert spec.display_name == "石油及其他液体产量"
