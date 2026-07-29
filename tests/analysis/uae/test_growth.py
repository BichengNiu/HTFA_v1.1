import numpy as np
import pandas as pd
import pytest

from dashboard.analysis.uae.growth import (
    calculate_diffusion,
    calculate_growth_contributions,
    calculate_nominal_real_bridge,
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


def test_additivity_reports_residual_instead_of_hiding_it():
    total = quarterly([100, 105], "total")
    components = {
        "a": quarterly([40, 42], "a"),
        "b": quarterly([50, 51], "b"),
    }

    result = validate_additivity(total, components)

    assert result.residual.iloc[-1] == pytest.approx(12.0)
    assert not result.within_tolerance.iloc[-1]


def test_nominal_real_bridge_is_log_additive():
    nominal = quarterly([100, 110], "nominal")
    real = quarterly([100, 105], "real")

    result = calculate_nominal_real_bridge(nominal, real, periods=1)

    assert (
        result.real_log_growth + result.deflator_log_growth
    ).iloc[-1] == pytest.approx(result.nominal_log_growth.iloc[-1])


def test_diffusion_excludes_missing_industries_from_denominator():
    industries = pd.DataFrame(
        {
            "a": [100, 105],
            "b": [100, 95],
            "c": [100, float("nan")],
        },
        index=pd.period_range("2024Q1", periods=2, freq="Q"),
    )

    result = calculate_diffusion(industries, periods=1)

    assert result.iloc[-1] == pytest.approx(0.5)


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
