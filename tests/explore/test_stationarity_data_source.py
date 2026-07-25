from io import BytesIO
from pathlib import Path

import pandas as pd

from dashboard.explore.core.data_source import (
    fingerprint_uploaded_file,
    format_table_option,
    load_stationarity_tables,
)


def _uae_workbook() -> Path:
    files = list((Path(__file__).parents[2] / "data").glob("*.xlsx"))
    assert len(files) == 1
    return files[0]


def test_uae_database_is_parsed_into_nonempty_frequency_tables():
    tables = load_stationarity_tables(_uae_workbook())

    assert list(tables) == ["daily", "monthly", "quarterly", "yearly"]
    assert tables["daily"].shape == (5766, 1)
    assert tables["monthly"].shape == (307, 1)
    assert tables["quarterly"].shape == (56, 24)
    assert tables["yearly"].shape == (46, 3)
    assert all(isinstance(frame.index, pd.DatetimeIndex) for frame in tables.values())
    assert format_table_option("quarterly", tables) == "季度数据（56 行 × 24 个指标）"


def test_file_fingerprint_detects_same_name_with_different_content():
    first = BytesIO(b"first")
    first.name = "database.xlsx"
    second = BytesIO(b"second")
    second.name = "database.xlsx"

    assert fingerprint_uploaded_file(first) != fingerprint_uploaded_file(second)


def test_csv_is_kept_as_a_single_table():
    uploaded = BytesIO("date,value\n2026-01-01,1\n".encode())
    uploaded.name = "series.csv"

    tables = load_stationarity_tables(uploaded)

    assert list(tables) == ["table"]
    assert tables["table"].shape == (1, 2)
