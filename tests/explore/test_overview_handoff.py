from __future__ import annotations

from dashboard.core.ui.utils.shared_dataset import SharedDatasetSnapshot
from dashboard.core.workspace import FileAsset
from dashboard.explore.core.overview_handoff import (
    OverviewHandoff,
    OverviewHandoffStore,
)


def _handoff() -> OverviewHandoff:
    return OverviewHandoff(
        dataset=SharedDatasetSnapshot(
            asset=FileAsset(
                slot="shared",
                name="sample.csv",
                content=b"date,value\n2025-01-01,1\n",
                fingerprint="file-fingerprint",
            ),
            sheet=None,
        ),
        widget_state={"univariate_overview_preview_variable_name_row": 1},
    )


def test_handoff_token_is_opaque_and_returns_an_independent_snapshot():
    clock = [10.0]
    store = OverviewHandoffStore(clock=lambda: clock[0])
    token = store.create(_handoff())

    assert store.is_valid(token)
    assert "sample.csv" not in token
    assert "date" not in token
    restored = store.get(token)
    assert restored is not None
    restored.widget_state["univariate_overview_preview_variable_name_row"] = 3

    assert (
        store.get(token).widget_state[
            "univariate_overview_preview_variable_name_row"
        ]
        == 1
    )


def test_handoff_token_expires_and_replace_removes_previous_token():
    clock = [10.0]
    store = OverviewHandoffStore(ttl_seconds=30, clock=lambda: clock[0])
    first = store.create(_handoff())
    second = store.replace(first, _handoff())

    assert first != second
    assert store.get(first) is None
    clock[0] = 40.0
    assert not store.is_valid(second)
    assert store.get(second) is None


def test_invalid_token_types_are_treated_as_missing():
    store = OverviewHandoffStore()

    assert store.get([]) is None
    assert not store.is_valid([])
