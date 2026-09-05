from __future__ import annotations

from io import BytesIO

import pandas as pd

from htfa.workspace import SessionWorkspace
from htfa.models.dfm.train.ui.components.file_uploader_component import (
    FileUploaderComponent,
)


class _State:
    def __init__(self):
        self.values = {}

    def get(self, _key, default=None):
        return self.values.get(_key, default)

    def set(self, key, value):
        self.values[key] = value

    def has(self, key):
        return key in self.values

    def delete(self, key):
        self.values.pop(key, None)


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


def test_dfm_training_loader_uses_the_tabular_input_protocol() -> None:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=2, freq="MS"),
                "A": [1.0, 2.0],
            }
        ).to_excel(writer, sheet_name="数据", index=False)
        pd.DataFrame(
            {
                "指标名称": ["A"],
                "行业": ["金融"],
                "单位": ["点"],
                "频率": ["M"],
                "预测变量": ["是"],
            }
        ).to_excel(writer, sheet_name="映射", index=False)
    output.seek(0)
    output.name = "prepared.xlsx"

    uploader = FileUploaderComponent(_State())
    input_df, industry_map, default_map, frequency_map, unit_map = (
        uploader._load_excel_file(output, object())
    )

    assert isinstance(input_df.index, pd.DatetimeIndex)
    assert input_df["A"].tolist() == [1.0, 2.0]
    assert industry_map == {"a": "金融"}
    assert default_map == {"a": "是"}
    assert frequency_map == {"a": "M"}
    assert unit_map == {"a": "点"}
