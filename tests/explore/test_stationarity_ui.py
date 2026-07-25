import numpy as np
import pandas as pd

from dashboard.explore.ui.stationarity import (
    StationarityAnalysisComponent,
    resolve_table_frequency,
    transformation_options_for_frequency,
)


def _component_with_memory(monkeypatch, initial):
    component = StationarityAnalysisComponent()
    memory = dict(initial)
    monkeypatch.setattr(
        component,
        "get_state",
        lambda key, default=None: memory.get(key, default),
    )
    monkeypatch.setattr(
        component,
        "set_state",
        lambda key, value: memory.__setitem__(key, value),
    )
    return component, memory


def test_selection_change_invalidates_all_derived_results(monkeypatch):
    component, memory = _component_with_memory(
        monkeypatch,
        {
            "selected_variable": "old",
            "test_results": pd.DataFrame({"x": [1]}),
            "test_signature": ("old",),
            "processed_data": pd.DataFrame({"x": [1]}),
        },
    )

    changed = component._remember_selection("selected_variable", "new")

    assert changed is True
    assert memory["selected_variable"] == "new"
    assert all(memory[key] is None for key in component._RESULT_STATE_KEYS)


def test_unchanged_selection_preserves_results(monkeypatch):
    results = pd.DataFrame({"x": [1]})
    component, memory = _component_with_memory(
        monkeypatch,
        {
            "selected_variable": "same",
            "test_results": results,
            "test_signature": ("same",),
        },
    )

    changed = component._remember_selection("selected_variable", "same")

    assert changed is False
    assert memory["test_results"] is results
    assert memory["test_signature"] == ("same",)


def test_frequency_table_key_has_priority_over_index_inference():
    series = pd.Series(
        np.arange(10.0),
        index=pd.date_range("2025-01-01", periods=10, freq="D"),
    )

    assert resolve_table_frequency("monthly", series) == "Monthly"


def test_csv_table_frequency_is_inferred_from_datetime_index():
    series = pd.Series(
        np.arange(24.0),
        index=pd.date_range("2024-01-31", periods=24, freq="ME"),
    )

    assert resolve_table_frequency("table", series) == "Monthly"


def test_unsupported_frequency_hides_year_over_year_options():
    options = transformation_options_for_frequency("Daily")

    assert "year_over_year" not in options
    assert "log_year_over_year" not in options
    assert "first_difference" in options
