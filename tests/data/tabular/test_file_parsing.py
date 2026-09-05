"""纯表格输入 parser 的行为契约。"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from htfa.data.tabular.file_parsing import (
    FileParseError,
    build_dataframe_from_rows,
    list_excel_sheets,
    load_dataframe,
    read_raw_rows,
)
from htfa.data.file_content import file_fingerprint


def test_file_fingerprint_depends_only_on_content():
    content = b"date,value\n2025-01-31,1\n"

    assert file_fingerprint(content) == file_fingerprint(content)
    assert file_fingerprint(content) != file_fingerprint(content + b"\n")


@pytest.mark.parametrize("encoding", ["utf-8", "gbk", "gb2312"])
def test_read_raw_rows_decodes_supported_csv_encodings(encoding):
    content = "日期,数值\n2025-01-31,1\n".encode(encoding)

    assert read_raw_rows(content, "data.csv") == [
        ["日期", "数值"],
        ["2025-01-31", "1"],
    ]


def test_load_dataframe_parses_csv_and_infers_numeric_and_time_columns():
    content = b"date,value\n2025-01-31,1.5\n2025-02-28,2.5\n"

    result = load_dataframe(content, "data.csv")

    assert result.columns.tolist() == ["date", "value"]
    assert pd.api.types.is_datetime64_any_dtype(result["date"])
    assert result["value"].tolist() == [1.5, 2.5]


def test_load_dataframe_infers_numeric_columns_with_blank_cells():
    """CSV 数值列含空单元格时仍保留为可建模的数值列。"""
    content = b"date,value,exog\n2025-01-31,1.5,10\n2025-02-28,2.5,\n"

    result = load_dataframe(content, "data.csv")

    assert pd.api.types.is_numeric_dtype(result["exog"])
    assert result["exog"].iloc[0] == 10.0
    assert pd.isna(result["exog"].iloc[1])


def test_load_dataframe_uses_selected_rows_and_explicit_time_column():
    content = (
        "说明行\n"
        "sales,date\n"
        "10,2020-01-01\n"
        "11,2020-02-01\n"
    ).encode()

    result = load_dataframe(
        content,
        "data.csv",
        variable_name_row=1,
        data_start_row=2,
        time_column="date",
    )

    assert result.columns.tolist() == ["sales", "date"]
    assert result["sales"].tolist() == [10, 11]
    assert result["date"].tolist() == [
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2020-02-01"),
    ]


def test_build_dataframe_can_explicitly_leave_time_column_unparsed():
    rows = [["date", "value"], ["not-a-date", 3]]

    result = build_dataframe_from_rows(rows, time_column=None)

    assert result["date"].tolist() == ["not-a-date"]


def test_build_dataframe_suffixes_duplicate_names_and_ignores_blank_trailing_cells():
    rows = [
        ["date", "value", "value", None],
        ["2020-01-01", 1, 10, None],
    ]

    result = build_dataframe_from_rows(rows, time_column="date")

    assert result.columns.tolist() == ["date", "value", "value__2"]
    assert result["value"].tolist() == [1]
    assert result["value__2"].tolist() == [10]


def test_build_dataframe_rejects_nonblank_cells_beyond_header_width():
    rows = [["date", "value"], ["2020-01-01", 1, "unexpected"]]

    with pytest.raises(FileParseError, match="超过变量名行的列数"):
        build_dataframe_from_rows(rows)


@pytest.mark.parametrize(
    ("rows", "kwargs", "message"),
    [
        ([[], [1]], {}, "变量名行为空"),
        ([["date"], ["2020-01-01"]], {"data_start_row": 0}, "晚于变量名行"),
        ([["date"], ["2020-01-01"]], {"data_start_row": 3}, "超出数据范围"),
        ([["date"], ["not-a-date"]], {"time_column": "date"}, "无法解析"),
    ],
)
def test_build_dataframe_reports_structural_and_time_errors(rows, kwargs, message):
    with pytest.raises(FileParseError, match=message):
        build_dataframe_from_rows(rows, **kwargs)


def test_read_raw_rows_rejects_unsupported_file_format():
    with pytest.raises(FileParseError, match="不支持的文件格式：json"):
        read_raw_rows(b"{}", "data.json")


def test_excel_helpers_list_sheets_and_read_selected_sheet(tmp_path):
    path = tmp_path / "sample.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([["date", "value"], ["2020-01-01", 1]]).to_excel(
            writer,
            header=False,
            index=False,
            sheet_name="数据",
        )
        pd.DataFrame([["other"], [2]]).to_excel(
            writer,
            header=False,
            index=False,
            sheet_name="其他",
        )

    content = path.read_bytes()

    assert list_excel_sheets(content, path.name) == ["数据", "其他"]
    assert read_raw_rows(content, path.name, sheet_name="数据") == [
        ["date", "value"],
        ["2020-01-01", 1],
    ]


def test_file_parser_does_not_require_file_objects():
    content = io.BytesIO(b"date,value\n2025-01-31,1\n")

    with pytest.raises(TypeError):
        load_dataframe(content, "data.csv")
