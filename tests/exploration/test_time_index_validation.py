"""Explicit date inputs must fail before analysis can use a partial result."""

import pandas as pd
import pytest

from htfa.exploration.processing.series_utils import prepare_time_index


@pytest.mark.parametrize("dates", [["2026-01-01", "invalid"], ["2026-01-01", None]])
def test_invalid_date_column_raises_without_mutating_input(dates):
    frame = pd.DataFrame({"date": dates, "value": [1, 2]})
    original = frame.copy(deep=True)
    with pytest.raises(ValueError):
        prepare_time_index(frame, time_column="date")
    pd.testing.assert_frame_equal(frame, original)


def test_missing_explicit_column_raises_even_when_it_matches_index_name():
    frame = pd.DataFrame({"value": [1]}, index=pd.Index(["invalid"], name="date"))
    with pytest.raises(ValueError, match="date"):
        prepare_time_index(frame, time_column="date")


def test_valid_date_column_preserves_requested_column_and_input():
    frame = pd.DataFrame({"date": ["2026-01-01"], "value": [1]})
    result, column = prepare_time_index(frame, time_column="date", keep_column=False)
    assert column == "date"
    assert result.index.equals(pd.DatetimeIndex(["2026-01-01"], name="date"))
    assert result.columns.tolist() == ["value"]
    assert frame["date"].tolist() == ["2026-01-01"]
