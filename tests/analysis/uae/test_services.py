"""服务层测试：growth 面板构建与监测仪表盘入口。"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from dashboard.analysis.uae.contracts import (
    DataProvenance,
    ProvenanceKind,
    UAEDataBundle,
)
from dashboard.analysis.uae.indicator_catalog import (
    INDICATOR_SPECS,
    INDUSTRY_NAMES,
)
from dashboard.analysis.uae.services import (
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
        "非金融公司实际增加值增速与平减指数同比",
        "GDP部门拉动与石油产量同比",
        "非油实际GDP同比及行业拉动",
        "行业量价四象限图",
        "行业扩张广度指数",
        "行业增长集中度",
        "行业增长持续性与状态矩阵",
    ]
    trend = panel.series_groups["GDP部门拉动与石油产量同比"]
    assert "【真实】非石油经济部门拉动" in trend.columns
    assert "【真实】石油经济部门拉动" in trend.columns
    assert "【真实】石油及其他液体产量季度同比" in trend.columns
    pull = panel.series_groups["非油实际GDP同比及行业拉动"]
    assert "【真实】非油GDP同比" in pull.columns
    assert "其他行业" in pull.columns
    assert len(pull.columns) == 7
    assert panel.headline.uses_simulated_data is False


def test_growth_panel_rejects_industries_that_do_not_sum_to_nonoil() -> None:
    bundle = _make_bundle()
    first_industry = f"industry.{list(INDUSTRY_NAMES)[0]}.real"
    bundle.series_by_id[first_industry] = (
        bundle.series_by_id[first_industry] * 2
    )

    with pytest.raises(ValueError):
        build_growth_panel(bundle)


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
        BytesIO(_workbook_bytes()),
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