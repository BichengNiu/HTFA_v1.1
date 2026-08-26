from __future__ import annotations

from io import BytesIO

from dashboard.core.workspace import SessionWorkspace
from dashboard.models.DFM.train.ui.components.file_uploader_component import (
    FileUploaderComponent,
)


class _State:
    def get(self, _key, default=None):
        return default


def _upload(content: bytes, name: str) -> BytesIO:
    file_input = BytesIO(content)
    file_input.name = name
    return file_input


def test_dfm_file_slots_are_isolated() -> None:
    workspace = SessionWorkspace({})
    workspace.put_asset("dfm.prep", _upload(b"prep", "source.xlsx"))
    workspace.put_asset("dfm.train", _upload(b"train", "prepared.xlsx"))

    assert workspace.open_asset("dfm.prep").read() == b"prep"
    assert workspace.open_asset("dfm.train").read() == b"train"
    workspace.clear_asset("dfm.train")
    assert workspace.get_asset("dfm.prep") is not None


def test_dfm_training_cache_id_uses_content_not_name_or_size() -> None:
    uploader = FileUploaderComponent(_State())

    first = uploader._get_file_id(_upload(b"same", "one.xlsx"))
    renamed = uploader._get_file_id(_upload(b"same", "two.xlsx"))
    changed = uploader._get_file_id(_upload(b"diff", "one.xlsx"))

    assert first == renamed
    assert first != changed
