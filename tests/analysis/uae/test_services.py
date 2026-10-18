"""服务层测试：growth 面板构建与监测仪表盘入口。"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from tests.analysis.uae._helpers import report_source

from htfa.monitoring.uae.contracts import (
    DataProvenance,
    ProvenanceKind,
    UAEDataBundle,
)
from htfa.monitoring.uae.indicator_catalog import (
    INDICATOR_SPECS,
    INDUSTRY_NAMES,
)
from htfa.monitoring.uae.services import (
    build_growth_panel,
    build_monitoring_dashboard,
)

QUARTERS = pd.period_range("2022Q1", periods=16, freq="Q")
SOURCE_IDS = {
    "growth.real_gdp",
    "growth.nominal_gdp",
    "growth.nonoil_real_gdp",
    "growth.nonoil_nominal_gdp",
    "growth.nonfinancial_real_gdp",
    "growth.nonfinancial_nominal_gdp",
    "growth.real_gdp_yoy",
    "growth.nonoil_real_gdp_yoy",
    "growth.nonfinancial_real_gdp_yoy",
    "oil.crude_production",
}


def _series_by_id() -> dict[str, pd.Series]:
    real_industries: dict[str, pd.Series] = {}
    for industry_id in INDUSTRY_NAMES:
        base = list(INDUSTRY_NAMES).index(industry_id) + 1
        real_industries[industry_id] = pd.Series(
            [base * (2000 + 250 * t) for t in range(len(QUARTERS))],
            index=QUARTERS,
            dtype=float,
        )
    nonoil = sum(real_industries.values()).rename("nonoil")
    oil = pd.Series(
        [8000 + 500 * t for t in range(len(QUARTERS))],
        index=QUARTERS,
        dtype=float,
    )
    real_gdp = (nonoil + oil).rename("real_gdp")
    nonfinancial = pd.Series(
        [4000 + 300 * t for t in range(len(QUARTERS))],
        index=QUARTERS,
        dtype=float,
    )
    series_by_id = {
        "growth.real_gdp": real_gdp,
        "growth.nominal_gdp": real_gdp * 1.05,
        "growth.nonoil_real_gdp": nonoil,
        "growth.nonoil_nominal_gdp": nonoil * 1.08,
        "growth.nonfinancial_real_gdp": nonfinancial,
        "growth.nonfinancial_nominal_gdp": nonfinancial * 1.06,
        "oil.crude_production": pd.Series(
            [3000 + 100 * t for t in range(len(QUARTERS))],
            index=QUARTERS,
            dtype=float,
        ),
    }
    for indicator_id in (
        "growth.real_gdp_yoy",
        "growth.nonoil_real_gdp_yoy",
        "growth.nonfinancial_real_gdp_yoy",
        "growth.nominal_gdp_yoy",
        "growth.nonoil_nominal_gdp_yoy",
        "growth.nonfinancial_nominal_gdp_yoy",
        "oil.dubai_crude_price",
        "market.dfm_index",
        "bilateral.china_odi_flow",
        "bilateral.china_odi_stock",
    ):
        series_by_id[indicator_id] = pd.Series(
            [5.0] * len(QUARTERS),
            index=QUARTERS,
        )
    for industry_id, real in real_industries.items():
        series_by_id[f"industry.{industry_id}.real"] = real
        series_by_id[f"industry.{industry_id}.nominal"] = real * 1.08
    return series_by_id


def _provenance(indicator_id: str) -> DataProvenance:
    return DataProvenance(
        indicator_id=indicator_id,
        display_name=indicator_id,
        kind=ProvenanceKind.REAL,
        source="测试来源",
        frequency="季度",
        unit="百万迪拉姆",
        coverage="阿联酋全国",
        as_of="2026-08-13",
    )


def _make_bundle() -> UAEDataBundle:
    series_by_id = _series_by_id()
    return UAEDataBundle(
        series_by_id=series_by_id,
        provenance_by_id={
            indicator_id: _provenance(indicator_id)
            for indicator_id in series_by_id
        },
    )


def test_growth_panel_returns_all_expected_series_groups() -> None:
    panel = build_growth_panel(_make_bundle())

    assert panel.key == "growth"
    assert list(panel.series_groups) == [
        "实际GDP增速与GDP平减指数同比",
        "非石油实际GDP增速与非石油GDP平减指数同比",
        "非油非金融实际GDP增速与平减指数同比",
        "GDP部门拉动与石油产量同比",
        "非油实际GDP行业拉动",
        "行业量价四象限图",
        "行业扩张广度指数",
        "行业增长集中度",
        "行业增长持续性与状态矩阵",
    ]
    trend = panel.series_groups["GDP部门拉动与石油产量同比"]
    assert "非石油经济部门拉动" in trend.columns
    assert "石油经济部门拉动" in trend.columns
    assert "石油及其他液体产量季度同比" in trend.columns
    pull = panel.series_groups["非油实际GDP行业拉动"]
    assert "非油GDP同比" in pull.columns
    assert "其他行业" in pull.columns
    assert len(pull.columns) == 7
    assert panel.headline.uses_simulated_data is False


@pytest.mark.parametrize("prefix, title", [
    ("", "实际GDP增速与GDP平减指数同比"),
    ("nonoil_", "非石油实际GDP增速与非石油GDP平减指数同比"),
    ("derived", "非油非金融实际GDP增速与平减指数同比"),
])
def test_deflator_yoy_uses_nominal_to_real_gdp_ratio(prefix, title):
    bundle = _make_bundle()
    if prefix == "derived":
        frame = build_growth_panel(bundle).series_groups[title]
        nonoil_real = bundle.series_by_id["growth.nonoil_real_gdp"]
        finance_real = bundle.series_by_id["industry.finance_insurance.real"]
        nonoil_nominal = bundle.series_by_id["growth.nonoil_nominal_gdp"]
        finance_nominal = bundle.series_by_id["industry.finance_insurance.nominal"]
        real = nonoil_real.sub(finance_real)
        nominal = nonoil_nominal.sub(finance_nominal)
        deflator_yoy = frame["非油非金融GDP平减指数同比"]
        expected = ((nominal.iloc[-1] / real.iloc[-1])
                    / (nominal.iloc[-5] / real.iloc[-5]) - 1) * 100
        assert deflator_yoy.iloc[-1] == pytest.approx(expected)
        assert frame["非油非金融实际GDP当季同比"].iloc[-1] == pytest.approx(
            (real.iloc[-1] / real.iloc[-5] - 1) * 100
        )
        return
    nominal_id = f"growth.{prefix}nominal_gdp"
    real_id = f"growth.{prefix}real_gdp"
    nominal = bundle.series_by_id[nominal_id].copy()
    real = bundle.series_by_id[real_id]
    nominal.iloc[-1] = real.iloc[-1] * 1.10
    bundle.series_by_id[nominal_id] = nominal

    frame = build_growth_panel(bundle).series_groups[title]
    deflator = frame.loc[:, frame.columns.str.contains("平减指数同比")].iloc[:, 0]
    expected = ((nominal.iloc[-1] / real.iloc[-1])
                / (nominal.iloc[-5] / real.iloc[-5]) - 1) * 100
    assert deflator.iloc[-1] == pytest.approx(expected)


def test_macro_download_keeps_level_history_in_chronological_order() -> None:
    bundle = _make_bundle()
    for indicator_id in (
        "growth.real_gdp_yoy", "growth.nonoil_real_gdp_yoy",
    ):
        bundle.series_by_id[indicator_id] = bundle.series_by_id[indicator_id].iloc[4:]
    panel = build_growth_panel(bundle)
    for title in (
        "实际GDP增速与GDP平减指数同比",
        "非石油实际GDP增速与非石油GDP平减指数同比",
        "非油非金融实际GDP增速与平减指数同比",
    ):
        frame = panel.series_groups[title]
        assert frame.index.is_monotonic_increasing
        assert frame.index[0] == QUARTERS[0]
        assert frame.index[-1] == QUARTERS[-1]
        assert pd.isna(frame.iloc[0, 0])
        assert frame.iloc[0, 2:].notna().all()


def test_growth_panel_rejects_industries_that_do_not_sum_to_nonoil() -> None:
    bundle = _make_bundle()
    first_industry = f"industry.{list(INDUSTRY_NAMES)[0]}.real"
    bundle.series_by_id[first_industry] = (
        bundle.series_by_id[first_industry] * 2
    )

    with pytest.raises(ValueError):
        build_growth_panel(bundle)


def test_growth_panel_keeps_rounding_residual_and_different_price_release_dates():
    bundle = _make_bundle()
    for indicator_id in bundle.series_by_id:
        if indicator_id.startswith(("growth.", "industry.")) and not indicator_id.endswith("_yoy"):
            bundle.series_by_id[indicator_id] /= 1000
    bundle.series_by_id["growth.nonoil_real_gdp"] += 0.003
    for indicator_id, series in list(bundle.series_by_id.items()):
        if "nominal" in indicator_id:
            bundle.series_by_id[indicator_id] = series.iloc[:-1]
    panel = build_growth_panel(bundle)
    quadrant = panel.series_groups["行业量价四象限图"]
    assert str(QUARTERS[-1]) not in quadrant.index.get_level_values("季度").tolist()
    assert panel.series_groups["非油实际GDP行业拉动"].index[-1] == QUARTERS[-1]
    for title in (
        "实际GDP增速与GDP平减指数同比",
        "非石油实际GDP增速与非石油GDP平减指数同比",
        "非油非金融实际GDP增速与平减指数同比",
    ):
        values = panel.series_groups[title]
        assert values.index[-1] == QUARTERS[-1]
        assert pd.notna(values.iloc[-1, 0])
        assert pd.isna(values.iloc[-1, 1])
    from htfa.monitoring.uae.charts import build_industry_price_volume_quadrant_figure

    figure = build_industry_price_volume_quadrant_figure(quadrant, title="量价")
    assert figure.frames
    corrupted = quadrant.copy()
    corrupted.iloc[0, corrupted.columns.get_loc("实际GDP占非油GDP比例")] += 0.1
    with pytest.raises(ValueError, match="未加总为1"):
        build_industry_price_volume_quadrant_figure(corrupted, title="量价")


def test_growth_panel_reports_missing_required_indicators() -> None:
    bundle = _make_bundle()
    bundle.series_by_id.pop("oil.crude_production")

    with pytest.raises(ValueError, match="缺少必需指标"):
        build_growth_panel(bundle)


def _workbook_bytes() -> bytes:
    series_by_id = _series_by_id()
    aliases = [spec.aliases[0] for spec in INDICATOR_SPECS]
    values_by_alias = {
        spec.aliases[0]: series_by_id[spec.indicator_id]
        for spec in INDICATOR_SPECS
    }
    dates = [
        period.end_time.normalize() for period in QUARTERS
    ]
    metadata_rows = [
        ["季度指标", *aliases],
        ["指标名称", *aliases],
        ["频率", *(["季度"] * len(aliases))],
        ["单位", *(["百万迪拉姆"] * len(aliases))],
        ["来源", *(["阿联酋统计局"] * len(aliases))],
        ["更新时间", *(["2026-08-13"] * len(aliases))],
    ]
    data_rows = [
        [dates[index]]
        + [values_by_alias[alias].iloc[index] for alias in aliases]
        for index in range(len(QUARTERS))
    ]
    dictionary = pd.DataFrame(
        {
            "指标名称": aliases,
            "类型": ["指标"] * len(aliases),
            "行业": [""] * len(aliases),
            "数据来源": ["阿联酋统计局"] * len(aliases),
            "预测变量": [""] * len(aliases),
        }
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dictionary.to_excel(writer, sheet_name="指标字典", index=False)
        pd.DataFrame(
            metadata_rows + data_rows
        ).to_excel(
            writer,
            sheet_name="季度_测试",
            header=False,
            index=False,
        )
    return buffer.getvalue()


def test_monitoring_dashboard_builds_growth_panel_from_workbook() -> None:
    dashboard = build_monitoring_dashboard(
        report_source(BytesIO(_workbook_bytes())),
    )

    assert list(dashboard.panels) == ["growth"]
    assert dashboard.unavailable_panels == {}


def test_monitoring_dashboard_reports_unavailable_for_bad_workbook() -> None:
    dashboard = build_monitoring_dashboard(BytesIO(b"not an xlsx"))

    assert dashboard.panels == {}
    assert "growth" in dashboard.unavailable_panels


def test_growth_panel_reports_missing_nonoil_gdp() -> None:
    series_by_id = _series_by_id()
    del series_by_id["growth.nonoil_real_gdp"]

    with pytest.raises(ValueError, match="growth.nonoil_real_gdp"):
        build_growth_panel(
            UAEDataBundle(
                series_by_id=series_by_id,
                provenance_by_id={
                    indicator_id: _provenance(indicator_id)
                    for indicator_id in series_by_id
                },
            )
        )
