from htfa.monitoring.uae.indicator_catalog import (
    INDICATOR_SPECS,
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
