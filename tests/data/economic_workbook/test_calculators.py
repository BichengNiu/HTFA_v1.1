import numpy as np
import pandas as pd

from htfa.data.economic_workbook.shared.calculators import _calculate_reference_values


def test_yearly_reference_values_do_not_borrow_from_older_years():
    series = pd.Series(
        [100.0, 120.0],
        index=pd.to_datetime(["2023-12-31", "2025-12-31"]),
        name="指标",
    )

    references = _calculate_reference_values(
        series.to_frame(),
        series,
        pd.Timestamp("2025-12-31"),
        "yearly",
    )

    assert np.isnan(references["上年值"])
    assert references["两年前值"] == 100.0
