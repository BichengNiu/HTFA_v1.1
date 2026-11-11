"""Industry totals cannot be substituted with a different calculation."""

import pandas as pd
import pytest

from htfa.monitoring.industrial.processing.contribution_calculator import (
    calculate_group_contributions,
)


def inputs():
    index = pd.date_range("2026-01-01", periods=1)
    frame = pd.DataFrame({"细分行业": [100.0]}, index=index)
    weights = {"细分行业": {"weights_row": pd.Series({"权重_2026": 0.2})}}
    groups = {"制造业": ["细分行业"]}
    totals = pd.DataFrame({"制造业增速": [10.0]}, index=index)
    return frame, weights, groups, totals


@pytest.mark.parametrize("case", ["missing_data", "missing_mapping", "missing_group", "missing_column"])
def test_three_industries_require_explicit_total_data_and_mapping(case):
    frame, weights, groups, totals = inputs()
    mapping = {"制造业": "制造业增速"}
    if case == "missing_data":
        totals = None
    elif case == "missing_mapping":
        mapping = None
    elif case == "missing_group":
        mapping = {}
    else:
        totals = totals.rename(columns={"制造业增速": "other"})
    with pytest.raises(ValueError):
        calculate_group_contributions(
            frame, weights, groups, "三大产业_", totals, mapping,
        )


def test_three_industries_use_total_growth_while_other_groups_use_components():
    frame, weights, groups, totals = inputs()
    result = calculate_group_contributions(
        frame, weights, groups, "三大产业_", totals, {"制造业": "制造业增速"},
    )
    assert result.iloc[0, 0] == 2.0
    components = calculate_group_contributions(frame, weights, groups)
    assert components.iloc[0, 0] == 20.0
