from io import BytesIO

from htfa.exploration.core.data_source import (
    fingerprint_uploaded_file,
    load_stationarity_data,
)


def test_file_fingerprint_detects_same_name_with_different_content():
    first = BytesIO(b"first")
    first.name = "database.xlsx"
    second = BytesIO(b"second")
    second.name = "database.xlsx"

    assert fingerprint_uploaded_file(first) != fingerprint_uploaded_file(second)


def test_csv_is_kept_as_a_single_table():
    uploaded = BytesIO("date,value\n2026-01-01,1\n".encode())
    uploaded.name = "series.csv"

    tables, metadata = load_stationarity_data(uploaded)

    assert list(tables) == ["table"]
    assert tables["table"].shape == (1, 2)
    assert metadata == {}
