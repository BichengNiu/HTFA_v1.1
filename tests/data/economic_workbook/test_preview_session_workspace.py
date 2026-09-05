from __future__ import annotations

from io import BytesIO

from htfa.workspace import SessionWorkspace
from htfa.data.economic_workbook.modules import create_economic_workbook_renderer


def _upload(content: bytes, name: str) -> BytesIO:
    file_input = BytesIO(content)
    file_input.name = name
    return file_input


def test_preview_renderers_use_isolated_workspace_slots() -> None:
    state: dict = {}
    workspace = SessionWorkspace(state)
    industrial = create_economic_workbook_renderer("industrial")
    uae = create_economic_workbook_renderer("uae")

    workspace.put_asset(industrial._asset_slot(), _upload(b"industrial", "cn.xlsx"))
    workspace.put_asset(uae._asset_slot(), _upload(b"uae", "uae.xlsx"))

    industrial_file = workspace.open_asset(industrial._asset_slot())
    uae_file = workspace.open_asset(uae._asset_slot())
    assert industrial_file is not None and industrial_file.name == "cn.xlsx"
    assert uae_file is not None and uae_file.name == "uae.xlsx"
    assert industrial_file.read() == b"industrial"
    assert uae_file.read() == b"uae"


def test_clearing_one_preview_slot_does_not_touch_the_other() -> None:
    state: dict = {}
    workspace = SessionWorkspace(state)
    workspace.put_asset(
        "economic_workbook.industrial", _upload(b"industrial", "cn.xlsx")
    )
    workspace.put_asset("economic_workbook.uae", _upload(b"uae", "uae.xlsx"))

    assert workspace.clear_asset("economic_workbook.industrial") is True
    assert workspace.get_asset("economic_workbook.industrial") is None
    assert workspace.get_asset("economic_workbook.uae") is not None
