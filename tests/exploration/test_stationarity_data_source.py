from io import BytesIO

from htfa.data.file_content import file_fingerprint, read_file_bytes
from htfa.data.tabular import TabularInputSource


TABULAR_SOURCE = TabularInputSource()


def test_file_fingerprint_detects_same_name_with_different_content():
    first = BytesIO(b"first")
    first.name = "database.xlsx"
    second = BytesIO(b"second")
    second.name = "database.xlsx"

    assert file_fingerprint(read_file_bytes(first)) != file_fingerprint(
        read_file_bytes(second)
    )


def test_csv_is_kept_as_a_single_table():
    uploaded = BytesIO("date,value\n2026-01-01,1\n".encode())
    uploaded.name = "series.csv"

    tables = TABULAR_SOURCE.read(uploaded, uploaded.name)

    assert list(tables) == ["table"]
    assert tables["table"].shape == (1, 2)
