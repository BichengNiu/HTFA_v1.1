import pandas as pd
import pytest

from dashboard.analysis.uae.contracts import (
    ConfidenceLevel,
    ProvenanceKind,
)
from dashboard.analysis.uae.data_adapter import (
    DEFAULT_UAE_WORKBOOK,
    load_runtime_uae_bundle,
)
from dashboard.analysis.uae.indicator_catalog import INDUSTRY_NAMES
from dashboard.analysis.uae.services import (
    build_growth_panel,
    build_monitoring_dashboard,
)


@pytest.fixture(scope="module")
def dashboard_result():
    return build_monitoring_dashboard(DEFAULT_UAE_WORKBOOK)


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
        if panel.key != "growth":
            assert panel.metrics
        assert panel.series_groups
        assert panel.headline.summary
        assert panel.headline.evidence
        assert panel.headline.limitation
        assert panel.methodology_notes


def test_simulation_caps_mixed_or_simulated_headlines_at_low(
    dashboard_result,
):
    for panel in dashboard_result.panels.values():
        if not panel.headline.uses_simulated_data:
            continue
        assert panel.headline.confidence is ConfidenceLevel.LOW
        assert any(
            "模拟数据" in reason
            for reason in panel.headline.confidence_reasons
        )


def test_growth_uses_real_results_without_legacy_bridge_or_residual():
    bundle = load_runtime_uae_bundle(DEFAULT_UAE_WORKBOOK)
    panel = build_growth_panel(bundle)

    assert panel.provenance["growth.real_gdp"].kind is ProvenanceKind.REAL
    assert panel.metrics == ()
    assert "石油机制证据" not in panel.series_groups
    assert "名义—实际桥接" not in panel.series_groups
    assert list(panel.series_groups)[:3] == [
        "实际GDP增速与GDP平减指数同比",
        "非石油实际GDP增速与非石油GDP平减指数同比",
        "非金融公司实际增加值增速与平减指数同比",
    ]
    assert "非油实际GDP同比及行业拉动" in panel.series_groups
    assert "GDP部门拉动与石油产量同比" in panel.series_groups
    assert "实际GDP增速与非石油经济部门拉动率" not in panel.series_groups
    assert panel.decomposition_tables == {}
    assert all(
        item.label != "迪拜原油价格同比"
        for item in panel.headline.evidence
    )


@pytest.mark.parametrize(
    (
        "group_title",
        "nominal_id",
        "real_id",
        "real_yoy_id",
        "real_label",
        "deflator_label",
    ),
    (
        (
            "实际GDP增速与GDP平减指数同比",
            "growth.nominal_gdp",
            "growth.real_gdp",
            "growth.real_gdp_yoy",
            "实际GDP当季同比",
            "GDP平减指数同比",
        ),
        (
            "非石油实际GDP增速与非石油GDP平减指数同比",
            "growth.nonoil_nominal_gdp",
            "growth.nonoil_real_gdp",
            "growth.nonoil_real_gdp_yoy",
            "非石油实际GDP当季同比",
            "非石油GDP平减指数同比",
        ),
        (
            "非金融公司实际增加值增速与平减指数同比",
            "growth.nonfinancial_nominal_gdp",
            "growth.nonfinancial_real_gdp",
            "growth.nonfinancial_real_gdp_yoy",
            "非金融公司实际增加值当季同比",
            "非金融公司GDP平减指数同比",
        ),
    ),
)
def test_growth_price_volume_charts_use_direct_real_yoy_and_deflator_yoy(
    group_title,
    nominal_id,
    real_id,
    real_yoy_id,
    real_label,
    deflator_label,
):
    bundle = load_runtime_uae_bundle(DEFAULT_UAE_WORKBOOK)
    panel = build_growth_panel(bundle)
    frame = panel.series_groups[group_title]

    assert list(frame.columns) == [
        f"【真实】{real_label}",
        f"【真实】{deflator_label}",
    ]
    pd.testing.assert_series_equal(
        frame[f"【真实】{real_label}"],
        bundle.require_series(real_yoy_id).rename(
            f"【真实】{real_label}"
        ),
        check_freq=False,
    )

    nominal = bundle.require_series(nominal_id)
    real = bundle.require_series(real_id)
    deflator = nominal / real * 100
    expected_deflator_yoy = (
        deflator.div(deflator.shift(4)).sub(1).mul(100)
    ).dropna().rename(
        f"【真实】{deflator_label}"
    )
    pd.testing.assert_series_equal(
        frame[f"【真实】{deflator_label}"],
        expected_deflator_yoy,
        check_freq=False,
    )


def test_fixed_top_five_average_share_industry_pulls_reconcile_to_growth():
    bundle = load_runtime_uae_bundle(DEFAULT_UAE_WORKBOOK)
    panel = build_growth_panel(bundle)
    frame = panel.series_groups["非油实际GDP同比及行业拉动"]
    line = frame["【真实】非油GDP同比"]
    bars = frame.drop(columns="【真实】非油GDP同比")

    assert len(bars.columns) == 6
    assert "其他行业" in bars.columns
    assert "采矿和采石" not in bars.columns
    assert bars.notna().sum(axis=1).eq(6).all()
    pd.testing.assert_series_equal(
        bars.sum(axis=1).rename("【真实】非油GDP同比"),
        line,
        check_exact=False,
        rtol=1e-9,
        atol=1e-8,
    )
    quarters = pd.DatetimeIndex(frame.index).to_period("Q")
    assert quarters.min() == pd.Period("2013Q1")
    assert quarters.max() == pd.Period("2025Q4")

    nonoil = bundle.require_series("growth.nonoil_real_gdp")
    levels = pd.DataFrame(
        {
            display_name: bundle.require_series(
                f"industry.{industry_id}.real"
            )
            for industry_id, (_, display_name) in INDUSTRY_NAMES.items()
        }
    )
    expected_top = list(
        levels.div(nonoil, axis=0).mean().nlargest(5).index
    )
    assert list(bars.columns[:-1]) == expected_top

    raw = levels.sub(levels.shift(4)).div(nonoil.shift(4), axis=0).mul(100)
    latest = frame.index[-1]
    assert bars.loc[latest, "其他行业"] == pytest.approx(
        raw.loc[latest].drop(index=expected_top).sum()
    )


def test_industry_price_volume_quadrant_uses_yoy_and_reconciled_real_shares():
    bundle = load_runtime_uae_bundle(DEFAULT_UAE_WORKBOOK)
    panel = build_growth_panel(bundle)
    frame = panel.series_groups["行业量价四象限图"]

    assert frame.index.names == ["季度", "行业"]
    assert list(frame.columns) == [
        "实际增加值增速",
        "行业隐含平减指数增速",
        "实际GDP占非油GDP比例",
    ]
    assert frame.index.get_level_values("季度").unique().tolist() == [
        str(period)
        for period in pd.period_range("2013Q1", "2025Q4", freq="Q")
    ]
    assert frame.groupby(level="季度").size().eq(len(INDUSTRY_NAMES)).all()
    assert frame.groupby(level="季度")[
        "实际GDP占非油GDP比例"
    ].sum().sub(1).abs().lt(1e-8).all()

    industry_id = "manufacturing"
    industry_name = INDUSTRY_NAMES[industry_id][1]
    nominal = bundle.require_series(f"industry.{industry_id}.nominal")
    real = bundle.require_series(f"industry.{industry_id}.real")
    nonoil = bundle.require_series("growth.nonoil_real_gdp")
    deflator = nominal.div(real).mul(100)
    latest = "2025Q4"

    assert frame.loc[(latest, industry_name), "实际增加值增速"] == pytest.approx(
        real.div(real.shift(4)).sub(1).mul(100).dropna().iloc[-1]
    )
    assert frame.loc[
        (latest, industry_name),
        "行业隐含平减指数增速",
    ] == pytest.approx(
        deflator.div(deflator.shift(4)).sub(1).mul(100).dropna().iloc[-1]
    )
    assert frame.loc[
        (latest, industry_name),
        "实际GDP占非油GDP比例",
    ] == pytest.approx((real / nonoil).dropna().iloc[-1])


def test_growth_panel_exposes_real_industry_quality_diagnostics():
    bundle = load_runtime_uae_bundle(DEFAULT_UAE_WORKBOOK)
    panel = build_growth_panel(bundle)

    assert {
        "行业扩张广度指数",
        "行业增长集中度",
        "行业增长持续性与状态矩阵",
    }.issubset(panel.series_groups)
    breadth = panel.series_groups["行业扩张广度指数"]
    concentration = panel.series_groups["行业增长集中度"]
    persistence = panel.series_groups["行业增长持续性与状态矩阵"]

    positive = breadth["不加权｜正增长行业比例"].dropna()
    quarters = pd.DatetimeIndex(positive.index).to_period("Q")
    assert len(positive) == 52
    assert quarters.min() == pd.Period("2013Q1")
    assert quarters.max() == pd.Period("2025Q4")
    assert positive.iloc[-1] == pytest.approx(93.75)
    assert breadth["加权｜正增长行业比例"].dropna().iloc[
        -1
    ] == pytest.approx(99.279, abs=1e-3)
    assert breadth[
        "加权｜增速较上季度加快的行业比例"
    ].dropna().iloc[-1] == pytest.approx(66.926, abs=1e-3)

    latest_concentration = concentration.dropna(
        subset=["正向贡献HHI", "加权增速标准差"]
    ).iloc[-1]
    assert latest_concentration[
        "前三行业净增长覆盖率"
    ] == pytest.approx(56.236, abs=1e-3)
    assert latest_concentration["正向贡献HHI"] == pytest.approx(
        0.133877,
        abs=1e-6,
    )
    assert latest_concentration["加权增速标准差"] == pytest.approx(
        3.258837,
        abs=1e-6,
    )

    latest_persistence = persistence.xs("2025Q4", level="季度")
    assert len(latest_persistence) == len(INDUSTRY_NAMES)
    assert latest_persistence["行业状态"].value_counts().to_dict() == {
        "高位加速": 6,
        "低位恶化": 5,
        "高位放缓": 3,
        "低位改善": 2,
    }


def test_growth_panel_calculates_nonoil_pull_from_real_levels():
    bundle = load_runtime_uae_bundle(DEFAULT_UAE_WORKBOOK)
    panel = build_growth_panel(bundle)
    frame = panel.series_groups[
        "GDP部门拉动与石油产量同比"
    ]
    real_gdp = bundle.require_series("growth.real_gdp")
    nonoil = bundle.require_series("growth.nonoil_real_gdp")
    expected = (
        (nonoil - nonoil.shift(4))
        .div(real_gdp.shift(4))
        .mul(100)
        .dropna()
        .rename("【真实】非石油经济部门拉动")
    )
    oil = real_gdp - nonoil
    expected_oil = (
        (oil - oil.shift(4))
        .div(real_gdp.shift(4))
        .mul(100)
        .dropna()
        .rename("【真实】石油经济部门拉动")
    )

    pd.testing.assert_series_equal(
        frame["【真实】非石油经济部门拉动"],
        expected,
    )
    pd.testing.assert_series_equal(
        frame["【真实】石油经济部门拉动"],
        expected_oil,
    )
    expected_total_growth = (
        real_gdp.div(real_gdp.shift(4)).sub(1).mul(100)
    ).dropna().rename("实际GDP同比")
    pd.testing.assert_series_equal(
        (
            frame["【真实】非石油经济部门拉动"]
            + frame["【真实】石油经济部门拉动"]
        ).rename("实际GDP同比"),
        expected_total_growth,
        check_exact=False,
        rtol=1e-10,
    )
    oil_production = bundle.require_series("oil.crude_production")
    expected_production_yoy = (
        oil_production.div(oil_production.shift(4)).sub(1).mul(100)
    ).reindex(expected_total_growth.dropna().index).rename(
        "【真实】石油及其他液体产量季度同比"
    )
    pd.testing.assert_series_equal(
        frame["【真实】石油及其他液体产量季度同比"],
        expected_production_yoy,
    )
    assert not any(
        "GDP同比" in column
        for column in frame.columns
    )
    quarters = pd.DatetimeIndex(frame.index).to_period("Q")
    assert quarters.min() == pd.Period("2013Q1")
    assert quarters.max() == pd.Period("2025Q4")
    assert panel.decomposition_tables == {}


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
