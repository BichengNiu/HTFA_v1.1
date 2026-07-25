from types import SimpleNamespace

from dashboard.core.ui.utils import state_helpers


def test_preview_state_is_isolated_by_namespace(monkeypatch):
    fake_streamlit = SimpleNamespace(session_state={})
    monkeypatch.setattr(state_helpers, "st", fake_streamlit)

    state_helpers.set_preview_state(
        "daily_df",
        "industrial-data",
        namespace="preview.industrial",
    )
    state_helpers.set_preview_state(
        "daily_df",
        "uae-data",
        namespace="preview.uae",
    )

    assert state_helpers.get_preview_state(
        "daily_df",
        namespace="preview.industrial",
    ) == "industrial-data"
    assert state_helpers.get_preview_state(
        "daily_df",
        namespace="preview.uae",
    ) == "uae-data"

    state_helpers.clear_preview_data(namespace="preview.uae")

    assert state_helpers.get_preview_state(
        "daily_df",
        namespace="preview.industrial",
    ) == "industrial-data"
    assert state_helpers.get_preview_state(
        "daily_df",
        namespace="preview.uae",
    ) is None
