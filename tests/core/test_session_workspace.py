from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from htfa.workspace import (
    SessionWorkspace,
    artifact_is_current,
    artifact_signature,
    stable_signature,
)


def _upload(content: bytes, name: str = "sample.xlsx") -> BytesIO:
    uploaded = BytesIO(content)
    uploaded.name = name
    return uploaded


def test_put_asset_only_marks_changed_when_content_changes() -> None:
    workspace = SessionWorkspace({})

    first = workspace.put_asset("shared", _upload(b"first"))
    repeated = workspace.put_asset("shared", _upload(b"first"))
    replaced = workspace.put_asset("shared", _upload(b"second"))

    assert first.changed is True
    assert repeated.changed is False
    assert replaced.changed is True
    assert first.asset.fingerprint != replaced.asset.fingerprint


def test_open_asset_returns_named_original_bytes() -> None:
    workspace = SessionWorkspace({})
    workspace.put_asset("shared", _upload(b"contents", "source.xlsm"))

    opened = workspace.open_asset("shared")

    assert opened is not None
    assert opened.name == "source.xlsm"
    assert opened.read() == b"contents"


def test_page_snapshot_restores_registered_values_only() -> None:
    state = {
        "page.scalar": "x",
        "page.list": ["a", "b"],
        "page.frame": pd.DataFrame({"value": [1, 2]}),
        "page.run": True,
    }
    workspace = SessionWorkspace(state)
    workspace.begin_page("page", keys=("page.scalar", "page.list", "page.frame"))
    workspace.end_page("page")

    del state["page.scalar"]
    del state["page.list"]
    del state["page.frame"]
    del state["page.run"]

    workspace.begin_page("page", keys=("page.scalar", "page.list", "page.frame"))

    assert state["page.scalar"] == "x"
    assert state["page.list"] == ["a", "b"]
    pd.testing.assert_frame_equal(state["page.frame"], pd.DataFrame({"value": [1, 2]}))
    assert "page.run" not in state


def test_page_snapshot_includes_registered_prefixes() -> None:
    state = {"dfm.variable.a": 1, "dfm.variable.b": 2, "other": 3}
    workspace = SessionWorkspace(state)
    workspace.begin_page("dfm", prefixes=("dfm.variable.",))
    workspace.end_page("dfm")
    del state["dfm.variable.a"]
    del state["dfm.variable.b"]

    workspace.begin_page("dfm", prefixes=("dfm.variable.",))

    assert state["dfm.variable.a"] == 1
    assert state["dfm.variable.b"] == 2
    assert state["other"] == 3


def test_reset_page_only_clears_the_target_page() -> None:
    state = {"first.value": 1, "second.value": 2}
    workspace = SessionWorkspace(state)
    workspace.begin_page("first", keys=("first.value",))
    workspace.end_page("first")
    workspace.begin_page("second", keys=("second.value",))
    workspace.end_page("second")

    workspace.reset_page("first")

    assert "first.value" not in state
    assert "workspace.pages.first.inputs" not in state
    assert state["second.value"] == 2
    assert state["workspace.pages.second.inputs"] == {"second.value": 2}


def test_signatures_are_canonical_and_reject_unknown_objects() -> None:
    first = stable_signature({"b": [1, 2], "a": "value"})
    second = stable_signature({"a": "value", "b": [1, 2]})
    current = artifact_signature(
        data_fingerprint="dataset", parameters={"lag": 2}, version="v1"
    )
    changed = artifact_signature(
        data_fingerprint="dataset", parameters={"lag": 3}, version="v1"
    )

    assert first == second
    assert current != changed
    assert artifact_is_current(current, current) is True
    assert artifact_is_current(None, current) is False
    with pytest.raises(TypeError):
        stable_signature({"unsupported": object()})
