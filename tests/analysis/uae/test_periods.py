"""Tests for shared UAE month-alignment helpers."""

import pandas as pd
import pytest

from dashboard.analysis.uae.periods import (
    anchor_last_month,
    common_latest_month,
    latest_complete_month,
    through_month,
    within_month_window,
)


def test_latest_complete_month_requires_all_columns() -> None:
    values = pd.DataFrame(
        {
            "a": [1.0, 2.0, 3.0],
            "b": [1.0, 2.0, float("nan")],
        },
        index=pd.date_range("2025-01-31", periods=3, freq="ME"),
    )

    assert latest_complete_month(values) == pd.Timestamp("2025-02-28")
    with pytest.raises(ValueError, match="共同完整月份"):
        latest_complete_month(
            pd.DataFrame(
                {"a": [float("nan")]},
                index=[values.index[-1]],
            )
        )


def test_anchor_last_month_skips_current_month() -> None:
    values = pd.DataFrame(
        {"value": [1.0, 2.0]},
        index=pd.to_datetime(["2025-04-30", "2025-05-31"]),
    )

    assert anchor_last_month(
        values,
        today=pd.Timestamp("2025-05-18"),
    ) == pd.Period("2025-04", freq="M")
    assert anchor_last_month(
        values,
        today=pd.Timestamp("2025-06-01"),
    ) == pd.Period("2025-05", freq="M")


def test_month_window_helpers_compare_months_not_day_timestamps() -> None:
    values = pd.Series(
        [1.0, 2.0, 3.0],
        index=pd.to_datetime(["2025-01-01", "2025-02-28", "2025-03-15"]),
    )

    window = within_month_window(
        values,
        first_month=pd.Period("2025-02", freq="M"),
        last_month=pd.Period("2025-03", freq="M"),
    )
    assert window.tolist() == [2.0, 3.0]
    assert through_month(values, pd.Period("2025-02", freq="M")).tolist() == [
        1.0,
        2.0,
    ]


def test_common_latest_month_uses_earliest_series_cutoff() -> None:
    index = pd.date_range("2025-01-31", periods=3, freq="ME")
    assert common_latest_month(
        [
            ("first", pd.Series([1.0, 2.0, 3.0], index=index)),
            ("second", pd.Series([1.0, 2.0], index=index[:2])),
        ]
    ) == pd.Period("2025-02", freq="M")
