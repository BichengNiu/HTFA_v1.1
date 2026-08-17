"""Tests for the shared metric-card helpers (latest value / MoM / YoY / render)."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from dashboard.analysis.uae.metrics import (
    change_in_points,
    latest_calendar_yoy_and_pp,
    latest_month_value,
    month_over_month_change,
    pct_delta_text,
    points_delta_text,
    render_metric_cards,
)


def _series(values, index):
    return pd.Series(values, index=pd.to_datetime(index))


def test_latest_month_value_skips_nan_tail() -> None:
    values = _series(
        [1.0, 2.0, None, None],
        ["2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31"],
    )

    value, as_of = latest_month_value(values)

    assert value == 2.0
    assert as_of == pd.Timestamp("2026-06-30")


def test_latest_month_value_empty_returns_none() -> None:
    value, as_of = latest_month_value(_series([], []))
    assert (value, as_of) == (None, None)


def test_month_over_month_change() -> None:
    values = _series(
        [100.0, 110.0, 132.0],
        ["2026-04-30", "2026-05-31", "2026-06-30"],
    )
    assert month_over_month_change(values) == pytest.approx(20.0)


def test_month_over_month_change_zero_or_singleton_is_none() -> None:
    assert month_over_month_change(_series([0.0, 5.0], ["2026-05-31", "2026-06-30"])) is None
    assert month_over_month_change(_series([5.0], ["2026-06-30"])) is None


def test_change_in_points() -> None:
    values = _series([3.5, 4.25], ["2026-07-31", "2026-08-31"])
    assert change_in_points(values) == pytest.approx(0.75)
    assert change_in_points(_series([3.5], ["2026-07-31"])) is None


def test_latest_calendar_yoy_and_pp_single_point() -> None:
    index = pd.date_range("2024-05-31", periods=13, freq="ME")
    values = pd.DataFrame({"X": [100.0] * 12 + [125.0]}, index=index)

    yoy, pp, as_of = latest_calendar_yoy_and_pp(values, "X")

    assert yoy == pytest.approx(25.0)
    assert pp is None  # 只有 1 个同比点，无从比较
    assert as_of == pd.Timestamp(index[-1])


def test_latest_calendar_yoy_and_pp_with_pp() -> None:
    index = pd.date_range("2024-05-31", periods=14, freq="ME")
    values = pd.DataFrame({"X": [100.0] * 12 + [125.0, 137.5]}, index=index)

    yoy, pp, as_of = latest_calendar_yoy_and_pp(values, "X")

    assert yoy == pytest.approx(37.5)
    assert pp == pytest.approx(12.5)


def test_format_deltas() -> None:
    assert pct_delta_text(12.34) == "环比 +12.3%"
    assert pct_delta_text(None) is None
    assert points_delta_text(0.75) == "较上月 +0.75 个百分点"
    assert points_delta_text(-0.5, unit="点", digits=1) == "较上月 -0.5 点"
    assert points_delta_text(None) is None


def test_render_metric_cards_renders_dash_for_missing() -> None:
    st_obj = MagicMock()
    st_obj.columns.return_value = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    render_metric_cards(
        st_obj,
        [
            ("A", "1", "环比 +1.0%", "help-a"),
            ("B", None, None, "help-b"),
            ("C", "3", "较上月 +0.10 个百分点", "help-c"),
            ("D", "4", "环比 +4.0%", "help-d"),
        ],
        n=4,
    )

    st_obj.columns.assert_called_once_with(4)
    assert st_obj.metric.call_count == 4
    args = [call.args for call in st_obj.metric.call_args_list]
    assert args[0][1] == "1"
    assert args[1][1] == "—"
    assert st_obj.metric.call_args_list[1].kwargs["delta"] is None
    assert args[2][1] == "3"
    assert all(
        call.kwargs["delta_color"] == "off"
        for call in st_obj.metric.call_args_list
    )
