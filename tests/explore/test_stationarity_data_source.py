from io import BytesIO
from pathlib import Path

import pandas as pd

from dashboard.explore.core.data_source import (
    fingerprint_uploaded_file,
    format_table_option,
    load_stationarity_tables,
)


def _uae_workbook() -> Path:
    workbook = Path(__file__).parents[2] / "data" / "阿联酋.xlsx"
    assert workbook.exists()
    return workbook


def test_uae_database_is_parsed_into_nonempty_frequency_tables():
    tables = load_stationarity_tables(_uae_workbook())

    assert list(tables) == ["daily", "weekly", "monthly", "quarterly"]
    for frame in tables.values():
        assert not frame.empty
        assert isinstance(frame.index, pd.DatetimeIndex)
        assert frame.index.is_monotonic_increasing
        assert not frame.index.has_duplicates

    quarterly = tables["quarterly"]
    assert format_table_option("quarterly", tables) == (
        f"季度数据（{len(quarterly)} 行 × {len(quarterly.columns)} 个指标）"
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

    tables = load_stationarity_tables(uploaded)

    assert list(tables) == ["table"]
    assert tables["table"].shape == (1, 2)
