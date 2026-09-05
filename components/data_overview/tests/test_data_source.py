"""数据源读取测试：跳行后首行作为变量名，并保留现有读取行为。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from data_overview.core.file_parsing import load_dataframe
from htfa.exploration.ui.shared_dataset_source import SharedDatasetSource
from htfa.exploration.ui import shared_dataset_source


class _UploadedFile:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self) -> bytes:
        return self._content


def _preamble_csv() -> bytes:
    return (
        "说明行一\n"
        "说明行二\n"
        "date,sales,exog\n"
        "2020-01-01,10,1\n"
        "2020-02-01,11,2\n"
    ).encode("utf-8")


def test_component_reader_uses_selected_row_as_header():
    uploaded = _UploadedFile("sample.csv", _preamble_csv())

    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        variable_name_row=2,
        data_start_row=3,
    )

    assert list(frame.columns) == ["date", "sales", "exog"]
    assert frame["date"].iloc[0] == pd.Timestamp("2020-01-01")
    assert frame["sales"].tolist() == [10, 11]


def test_shared_reader_preserves_default_header_behavior():
    uploaded = _UploadedFile("sample.csv", b"date,value\n2020-01-01,3\n")

    frame = load_dataframe(uploaded.getvalue(), uploaded.name)

    assert list(frame.columns) == ["date", "value"]
    assert frame["date"].iloc[0] == pd.Timestamp("2020-01-01")


def test_shared_reader_reuses_supplied_raw_rows_without_reopening_file(
    monkeypatch,
):
    """SARIMAX 复用当前工作表缓存时不应再次解析上传文件。"""
    uploaded = _UploadedFile("sample.xlsx", b"not-used")
    raw_rows = [
        ["date", "value"],
        ["2020-01-01", 3],
    ]

    def fail_if_file_is_read(*args, **kwargs):
        raise AssertionError("不应重新读取上传文件")

    monkeypatch.setattr(
        "data_overview.core.file_parsing.read_raw_rows",
        fail_if_file_is_read,
    )
    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        raw_rows=raw_rows,
        variable_name_row=0,
        data_start_row=1,
    )

    assert frame["value"].tolist() == [3]


def test_shared_source_passes_cached_rows_to_shared_reader(monkeypatch):
    """SARIMAX 数据源应把当前工作表缓存传给共享读取器。"""
    uploaded = _UploadedFile("sample.xlsx", b"not-used")
    raw_rows = [["date", "value"], ["2020-01-01", 3]]
    captured = {}

    monkeypatch.setattr(
        "htfa.app.state.shared_dataset.get_shared_dataset_file",
        lambda: uploaded,
    )
    monkeypatch.setattr(
        "htfa.app.state.shared_dataset.get_shared_dataset_raw_rows",
        lambda: raw_rows,
    )
    monkeypatch.setattr(
        "htfa.app.state.shared_dataset.get_shared_dataset_sheet",
        lambda: "数据",
    )

    def fake_load_dataframe(content, file_name, **kwargs):
        captured["content"] = content
        captured["file_name"] = file_name
        captured.update(kwargs)
        return pd.DataFrame({"value": [3]})

    monkeypatch.setattr(
        shared_dataset_source,
        "load_dataframe",
        fake_load_dataframe,
    )

    frame = SharedDatasetSource().load_data(
        variable_name_row=1,
        data_start_row=2,
        time_column="date",
    )

    assert frame["value"].tolist() == [3]
    assert captured["content"] == uploaded.getvalue()
    assert captured["file_name"] == uploaded.name
    assert captured["sheet_name"] == "数据"
    assert captured["raw_rows"] is raw_rows


def test_shared_reader_supports_selected_rows_with_irregular_preamble():
    uploaded = _UploadedFile("sample.csv", _preamble_csv())

    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        variable_name_row=2,
        data_start_row=3,
    )

    assert list(frame.columns) == ["date", "sales", "exog"]
    assert frame["exog"].tolist() == [1, 2]


def test_reader_parses_user_selected_time_column():
    uploaded = _UploadedFile(
        "sample.csv",
        b"sales,date\n10,2020-01-01\n11,2020-02-01\n",
    )

    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        variable_name_row=0,
        data_start_row=1,
        time_column="date",
    )

    assert frame["date"].tolist() == [
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2020-02-01"),
    ]
    assert frame["sales"].tolist() == [10, 11]


def test_reader_can_leave_time_column_unparsed():
    uploaded = _UploadedFile("sample.csv", b"date,value\nnot-a-date,3\n")

    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        variable_name_row=0,
        data_start_row=1,
        time_column=None,
    )

    assert frame["date"].tolist() == ["not-a-date"]


def test_reader_reports_invalid_selected_time_column():
    uploaded = _UploadedFile("sample.csv", b"date,value\nnot-a-date,3\n")

    with pytest.raises(ValueError, match="无法解析"):
        load_dataframe(
            uploaded.getvalue(),
            uploaded.name,
            variable_name_row=0,
            data_start_row=1,
            time_column="date",
        )


def test_reader_suffixes_duplicate_variable_names():
    uploaded = _UploadedFile(
        "duplicate.csv",
        b"date,value,value\n2020-01-01,1,10\n2020-02-01,2,20\n",
    )

    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        variable_name_row=0,
        data_start_row=1,
        time_column="date",
    )

    assert list(frame.columns) == ["date", "value", "value__2"]
    assert frame["value"].tolist() == [1, 2]
    assert frame["value__2"].tolist() == [10, 20]


def test_shared_reader_suffixes_duplicate_variable_names():
    uploaded = _UploadedFile(
        "duplicate.csv",
        b"date,value,value\n2020-01-01,1,10\n",
    )

    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        variable_name_row=0,
        data_start_row=1,
        time_column="date",
    )

    assert list(frame.columns) == ["date", "value", "value__2"]


def test_reader_rejects_data_start_before_variable_name_row():
    uploaded = _UploadedFile("sample.csv", b"date,value\n2020-01-01,3\n")

    with pytest.raises(ValueError, match="晚于变量名行"):
        load_dataframe(
            uploaded.getvalue(),
            uploaded.name,
            variable_name_row=1,
            data_start_row=1,
        )


def test_reader_reports_when_data_start_removes_all_rows():
    uploaded = _UploadedFile("sample.csv", b"date,value\n2020-01-01,3\n")

    with pytest.raises(ValueError, match="超出数据范围"):
        load_dataframe(
            uploaded.getvalue(),
            uploaded.name,
            variable_name_row=0,
            data_start_row=10,
        )


def test_excel_reader_applies_selected_rows_before_data(tmp_path):
    path = tmp_path / "sample.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                ["说明行"],
                ["date", "sales"],
                ["2020-01-01", 10],
            ]
        ).to_excel(writer, header=False, index=False, sheet_name="数据")

    uploaded = _UploadedFile(path.name, path.read_bytes())
    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        sheet_name="数据",
        variable_name_row=1,
        data_start_row=2,
    )

    assert list(frame.columns) == ["date", "sales"]
    assert frame["date"].iloc[0] == pd.Timestamp("2020-01-01")


def test_excel_datetime_cells_are_not_converted_to_numeric_time(tmp_path):
    path = tmp_path / "datetime.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-02-01"]),
                "value": [1, 2],
            }
        ).to_excel(writer, index=False, sheet_name="数据")

    uploaded = _UploadedFile(path.name, path.read_bytes())
    frame = load_dataframe(
        uploaded.getvalue(),
        uploaded.name,
        sheet_name="数据",
        variable_name_row=0,
        data_start_row=1,
        time_column="date",
    )

    assert frame["date"].tolist() == [
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2020-02-01"),
    ]
