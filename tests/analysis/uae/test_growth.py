import numpy as np
import pandas as pd
import pytest

from htfa.monitoring.uae.growth import (
    calculate_growth_contributions,
    calculate_industry_diagnostics,
    validate_additivity,
)


def quarterly(values, name):
    return pd.Series(
        values,
        index=pd.period_range("2024Q1", periods=len(values), freq="Q"),
        name=name,
        dtype=float,
    )


def test_yoy_contributions_sum_to_total_growth_when_components_add():
    oil = quarterly([30, 31, 32, 33, 33, 34, 35, 36], "oil")
    nonoil = quarterly([70, 72, 74, 76, 77, 79, 81, 84], "nonoil")
    total = oil + nonoil

    result = calculate_growth_contributions(
        total,
        {"oil": oil, "nonoil": nonoil},
        periods=4,
    )

    assert result.contributions.sum(axis=1).iloc[-1] == pytest.approx(
        result.total_growth.iloc[-1]
    )


def test_contribution_uses_level_changes_not_component_growth_rates():
    oil = quarterly([20, 40], "oil")
    nonoil = quarterly([80, 80], "nonoil")
    total = oil + nonoil

    result = calculate_growth_contributions(
        total,
        {"oil": oil, "nonoil": nonoil},
        periods=1,
    )

    assert result.total_growth.iloc[-1] == pytest.approx(20.0)
    assert result.contributions["oil"].iloc[-1] == pytest.approx(20.0)
    assert result.contributions["oil"].iloc[-1] != pytest.approx(100.0)


def test_additivity_reports_residual_instead_of_hiding_it():
    total = quarterly([100, 105], "total")
    components = {
        "a": quarterly([40, 42], "a"),
        "b": quarterly([50, 51], "b"),
    }

    result = validate_additivity(total, components)

    assert result.residual.iloc[-1] == pytest.approx(12.0)
    assert not result.within_tolerance.iloc[-1]


def test_contribution_rejects_nonpositive_lagged_total():
    total = quarterly([0, 100], "total")
    component = quarterly([0, 100], "component")

    with pytest.raises(ValueError, match="滞后总量必须为正"):
        calculate_growth_contributions(
            total,
            {"component": component},
            periods=1,
        )


def test_growth_calculations_preserve_missing_values():
    total = quarterly([100, np.nan, 110], "total")
    component = quarterly([100, np.nan, 110], "component")

    result = calculate_growth_contributions(
        total,
        {"component": component},
        periods=1,
    )

    assert result.total_growth.isna().iloc[1]
    assert result.contributions["component"].isna().iloc[1]


def test_industry_diagnostics_calculates_unweighted_and_weighted_breadth():
    index = pd.period_range("2022Q1", periods=12, freq="Q")
    components = {
        "a": pd.Series(
            [40, 42, 45, 47, 50, 53, 56, 59, 62, 65, 68, 72],
            index=index,
            dtype=float,
        ),
        "b": pd.Series(
            [30, 29, 31, 30, 32, 31, 33, 32, 34, 33, 35, 34],
            index=index,
            dtype=float,
        ),
        "c": pd.Series([20] * 12, index=index, dtype=float),
        "d": pd.Series(
            [10, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16],
            index=index,
            dtype=float,
        ),
    }
    total = sum(components.values()).rename("total")

    result = calculate_industry_diagnostics(
        total,
        components,
        periods=1,
        history_min_periods=3,
        persistence_window=4,
    )

    growth_rates = pd.DataFrame(components).pct_change(
        periods=1,
        fill_method=None,
    ).mul(100)
    base_year_shares = pd.DataFrame(components).shift(1).div(
        total.shift(1),
        axis=0,
    )
    positive = growth_rates.gt(0).where(
        growth_rates.notna()
    )
    complete = positive.notna().all(axis=1)
    expected_unweighted = (
        positive.astype(float).mean(axis=1).mul(100).where(complete)
    ).rename("不加权｜正增长行业比例")
    expected_weighted = (
        base_year_shares.mul(positive.astype(float))
        .sum(axis=1, min_count=len(components))
        .mul(100)
        .where(complete)
    ).rename("加权｜正增长行业比例")
    pd.testing.assert_series_equal(
        result.breadth["不加权｜正增长行业比例"],
        expected_unweighted,
    )
    pd.testing.assert_series_equal(
        result.breadth["加权｜正增长行业比例"],
        expected_weighted,
    )

    prior_history = (
        growth_rates.shift(1)
        .expanding(min_periods=3)
        .mean()
    )
    above_history = growth_rates.gt(prior_history).where(
        growth_rates.notna() & prior_history.notna()
    )
    expected_history_breadth = (
        above_history.astype(float)
        .mean(axis=1)
        .mul(100)
        .where(above_history.notna().all(axis=1))
    ).rename("不加权｜增速高于历史均值的行业比例")
    pd.testing.assert_series_equal(
        result.breadth["不加权｜增速高于历史均值的行业比例"],
        expected_history_breadth,
    )


def test_industry_diagnostics_builds_direction_concentration_map_metrics():
    index = pd.period_range("2025Q1", periods=2, freq="Q")
    components = {
        "a": pd.Series([30, 36], index=index, dtype=float),
        "b": pd.Series([25, 29], index=index, dtype=float),
        "c": pd.Series([25, 27], index=index, dtype=float),
        "d": pd.Series([20, 16], index=index, dtype=float),
    }
    total = sum(components.values()).rename("total")

    result = calculate_industry_diagnostics(
        total,
        components,
        periods=1,
        history_min_periods=1,
        persistence_window=1,
    )
    latest = index[-1]

    assert list(result.concentration) == [
        "贡献平衡指数",
        "标准化绝对贡献集中度",
        "绝对贡献HHI",
        "总变动强度",
        "非油GDP同比",
        "最大正向贡献行业",
        "最大正向贡献",
        "最大负向贡献行业",
        "最大负向贡献",
    ]
    expected_hhi = (
        (6 / 16) ** 2
        + (4 / 16) ** 2
        + (2 / 16) ** 2
        + (4 / 16) ** 2
    )
    assert result.concentration.loc[latest, "贡献平衡指数"] == 50
    assert result.concentration.loc[
        latest, "绝对贡献HHI"
    ] == pytest.approx(expected_hhi)
    assert result.concentration.loc[
        latest, "标准化绝对贡献集中度"
    ] == pytest.approx((expected_hhi - 1 / 4) / (1 - 1 / 4) * 100)
    assert result.concentration.loc[latest, "总变动强度"] == 16
    assert result.concentration.loc[latest, "非油GDP同比"] == 8
    assert result.concentration.loc[latest, "最大正向贡献行业"] == "a"
    assert result.concentration.loc[latest, "最大正向贡献"] == 6
    assert result.concentration.loc[latest, "最大负向贡献行业"] == "d"
    assert result.concentration.loc[latest, "最大负向贡献"] == -4

    shrinking_components = {
        "a": pd.Series([30, 32], index=index, dtype=float),
        "b": pd.Series([25, 26], index=index, dtype=float),
        "c": pd.Series([25, 22], index=index, dtype=float),
        "d": pd.Series([20, 15], index=index, dtype=float),
    }
    shrinking = calculate_industry_diagnostics(
        sum(shrinking_components.values()).rename("total"),
        shrinking_components,
        periods=1,
        history_min_periods=1,
        persistence_window=1,
    )
    shrinking_hhi = (2 / 11) ** 2 + (1 / 11) ** 2 + (3 / 11) ** 2 + (5 / 11) ** 2
    assert shrinking.concentration.loc[
        latest, "贡献平衡指数"
    ] == pytest.approx(-5 / 11 * 100)
    assert shrinking.concentration.loc[
        latest, "绝对贡献HHI"
    ] == pytest.approx(shrinking_hhi)
    assert shrinking.concentration.loc[
        latest, "标准化绝对贡献集中度"
    ] == pytest.approx((shrinking_hhi - 1 / 4) / (1 - 1 / 4) * 100)
    assert shrinking.concentration.loc[latest, "总变动强度"] == 11
    assert shrinking.concentration.loc[latest, "最大正向贡献行业"] == "a"
    assert shrinking.concentration.loc[latest, "最大负向贡献行业"] == "d"

    all_negative_components = {
        name: series - pd.Series([0, amount], index=index)
        for (name, series), amount in zip(
            components.items(),
            (7, 5, 3, 1),
        )
    }
    all_negative = calculate_industry_diagnostics(
        sum(all_negative_components.values()).rename("total"),
        all_negative_components,
        periods=1,
        history_min_periods=1,
        persistence_window=1,
    )
    assert all_negative.concentration.loc[latest, "贡献平衡指数"] == -100
    assert pd.notna(
        all_negative.concentration.loc[latest, "绝对贡献HHI"]
    )
    assert pd.isna(
        all_negative.concentration.loc[latest, "最大正向贡献行业"]
    )
    assert all_negative.concentration.loc[latest, "最大负向贡献行业"] == "d"


def test_industry_concentration_is_empty_when_industries_do_not_change():
    index = pd.period_range("2025Q1", periods=2, freq="Q")
    components = {
        "a": pd.Series([60, 60], index=index, dtype=float),
        "b": pd.Series([40, 40], index=index, dtype=float),
    }

    result = calculate_industry_diagnostics(
        sum(components.values()).rename("total"),
        components,
        periods=1,
        history_min_periods=1,
        persistence_window=1,
    )

    assert result.concentration.iloc[-1].isna().all()


def _levels_from_growth(
    growth_rates: list[float],
    *,
    start: float = 100.0,
) -> list[float]:
    levels = [start]
    for growth_rate in growth_rates:
        levels.append(levels[-1] * (1 + growth_rate / 100))
    return levels


def test_industry_diagnostics_builds_all_four_persistence_states():
    index = pd.period_range("2023Q1", periods=9, freq="Q")
    components = {
        "high_accelerating": pd.Series(
            _levels_from_growth([1, 1, 1, 1, 2, 3, 4, 5]),
            index=index,
        ),
        "high_slowing": pd.Series(
            _levels_from_growth([1, 1, 1, 1, 5, 4, 3, 2.5]),
            index=index,
        ),
        "low_improving": pd.Series(
            _levels_from_growth([5, 5, 5, 5, 1, 0, -2, -1]),
            index=index,
        ),
        "low_worsening": pd.Series(
            _levels_from_growth([5, 5, 5, 5, 1, 0, -1, -2]),
            index=index,
        ),
    }
    result = calculate_industry_diagnostics(
        sum(components.values()).rename("total"),
        components,
        periods=1,
        history_min_periods=3,
        persistence_window=4,
    )
    latest = str(index[-1])
    latest_frame = result.persistence.xs(latest, level="季度")

    assert latest_frame["行业状态"].to_dict() == {
        "high_accelerating": "高位加速",
        "high_slowing": "高位放缓",
        "low_improving": "低位改善",
        "low_worsening": "低位恶化",
    }
    assert latest_frame.loc[
        "high_accelerating", "连续正增长季度数"
    ] == 8
    assert latest_frame.loc[
        "low_improving", "连续正增长季度数"
    ] == 0
    assert latest_frame["最近4季度高于自身历史趋势次数"].between(
        0, 4
    ).all()
    expected_prior_four = (
        pd.DataFrame(components)["high_accelerating"]
        .pct_change(periods=1, fill_method=None)
        .mul(100)
        .shift(1)
        .rolling(4, min_periods=4)
        .mean()
        .iloc[-1]
    )
    assert latest_frame.loc[
        "high_accelerating", "当季增速减过去4季度均值"
    ] == pytest.approx(5 - expected_prior_four)


def test_industry_diagnostics_preserves_missing_quarters_and_rejects_gaps():
    index = pd.period_range("2024Q1", periods=6, freq="Q")
    a = pd.Series([40, 41, 42, 43, 44, 45], index=index, dtype=float)
    b_complete = pd.Series(
        [60, 61, 62, 63, 64, 65],
        index=index,
        dtype=float,
    )
    total = (a + b_complete).rename("total")
    b_missing = b_complete.copy()
    b_missing.iloc[3] = np.nan

    result = calculate_industry_diagnostics(
        total,
        {"a": a, "b": b_missing},
        periods=1,
        history_min_periods=2,
        persistence_window=2,
    )
    assert index[3] in result.breadth.index
    assert result.breadth.loc[index[3]].isna().all()

    gap_index = index.delete(3)
    with pytest.raises(ValueError, match="季度索引必须连续"):
        calculate_industry_diagnostics(
            total.reindex(gap_index),
            {
                "a": a.reindex(gap_index),
                "b": b_complete.reindex(gap_index),
            },
            periods=1,
            history_min_periods=2,
            persistence_window=2,
        )

    with pytest.raises(ValueError, match="行业权重之和"):
        calculate_industry_diagnostics(
            total + 5,
            {"a": a, "b": b_complete},
            periods=1,
            history_min_periods=2,
            persistence_window=2,
        )
