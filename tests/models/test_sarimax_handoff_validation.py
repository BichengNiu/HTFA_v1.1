"""Malformed handoff values must reach the page error boundary."""

from types import SimpleNamespace

import pytest

from htfa.models.univariate.sarimax.ui import standalone_model as standalone


@pytest.mark.parametrize("rows", [
    {"sarimax_model_preview_variable_name_row": "invalid"},
    {"sarimax_model_preview_data_start_row": "invalid"},
    {"sarimax_model_preview_variable_name_row": 0},
    {"sarimax_model_preview_variable_name_row": 2, "sarimax_model_preview_data_start_row": 1},
])
def test_invalid_handoff_rows_raise(rows):
    with pytest.raises(ValueError):
        standalone._read_handoff_rows(rows)


@pytest.mark.parametrize("dates", [
    ["invalid", "2026-01-31"], [None, "2026-01-31"], "invalid",
    ["2026-01-31"], ["2026-02-01", "2026-01-31"],
])
def test_invalid_handoff_dates_raise(monkeypatch, dates):
    stored = {}
    monkeypatch.setattr(
        standalone, "SARIMAX_SCOPE",
        SimpleNamespace(state=SimpleNamespace(set=lambda key, value: stored.update({key: value}))),
    )
    with pytest.raises(ValueError):
        standalone._seed_sarimax_input_state({"sarimax_train_forecast_window": dates})
    assert "training_time_range" not in stored


def test_default_and_explicit_handoff_rows_are_valid():
    assert standalone._read_handoff_rows({}) == (1, 2)
    assert standalone._read_handoff_rows({
        "sarimax_model_preview_variable_name_row": 2,
        "sarimax_model_preview_data_start_row": 4,
    }) == (2, 4)
