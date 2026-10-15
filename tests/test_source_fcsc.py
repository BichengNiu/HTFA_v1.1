"""FCSC UAE.Stat CPI ingestion and database contract."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

import duckdb
import pytest

from htfa.jobs.uae_data import db, source_fcsc


def _csv_payload(*, months: int = 24, duplicate: bool = False) -> bytes:
    records = [
        "STRUCTURE,STRUCTURE_ID,ACTION,MEASURE,UNIT_MEASURE,REF_AREA,FREQ,"
        "CPI_DIV,SOURCE_DETAIL,TIME_PERIOD,OBS_VALUE,DECIMALS,OBS_STATUS,UNIT_MULT"
    ]
    year, month = 2021, 1
    for index in range(months):
        period = f"{year:04d}-{month:02d}"
        for division, value in (("ALL", 100 + index * 0.2), ("FNB", 100 + index * 0.3)):
            records.append(
                f"DATA,FCSA:DF_CPI(3.2.0),I,CPI_INDEX21,INDX,AE,M,{division},"
                f"FCSA,{period},{value:.2f},2,,"
            )
        if duplicate and index == 0:
            records.append(
                f"DATA,FCSA:DF_CPI(3.2.0),I,CPI_INDEX21,INDX,AE,M,ALL,"
                f"FCSA,{period},100,2,,"
            )
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    # Irrelevant rows from the same dataflow must not enter the CPI index series.
    records.append(
        "DATA,FCSA:DF_CPI(3.2.0),I,CPI_ANNCHG21,PERCENT,AE,M,ALL,"
        "FCSA,2021-01,1.2,2,,"
    )
    return ("\n".join(records) + "\n").encode("utf-8")


def test_parse_cpi_csv_filters_national_monthly_2021_base_index():
    rows = source_fcsc.parse_cpi_csv(_csv_payload())
    assert len(rows) == 48
    assert rows[0] == {
        "period": date(2021, 1, monthrange(2021, 1)[1]),
        "indicator": source_fcsc.INDICATORS["ALL"],
        "value": 100.0,
        "source_file": source_fcsc.RAW_CSV.name,
    }
    assert rows[-1]["indicator"] == source_fcsc.INDICATORS["FNB"]
    assert rows[-1]["period"] == date(2022, 12, 31)


def test_parse_rejects_duplicate_or_incomplete_series():
    with pytest.raises(ValueError, match="重复观测"):
        source_fcsc.parse_cpi_csv(_csv_payload(duplicate=True))
    incomplete = _csv_payload().replace(
        b"DATA,FCSA:DF_CPI(3.2.0),I,CPI_INDEX21,INDX,AE,M,FNB,FCSA,2022-12,106.90,2,,\n",
        b"",
    )
    with pytest.raises(ValueError, match="期间不一致"):
        source_fcsc.parse_cpi_csv(incomplete)


def test_update_writes_duckdb_and_dictionary_from_cached_official_csv(tmp_path, monkeypatch):
    raw_csv = tmp_path / "df_cpi_3.2.0.csv"
    raw_csv.write_bytes(_csv_payload())
    monkeypatch.setattr(source_fcsc, "RAW_CSV", raw_csv)

    with duckdb.connect(":memory:") as con:
        db.init_schema(con)
        result = source_fcsc.update(con, skip_download=True)
        count = con.execute("SELECT count(*) FROM fcsc_monthly").fetchone()[0]
        latest = con.execute("SELECT max(period) FROM fcsc_monthly").fetchone()[0]
        metadata = con.execute(
            "SELECT frequency, unit, source FROM meta_indicator_dictionary "
            "WHERE indicator_name = ?",
            [source_fcsc.INDICATORS["FNB"]],
        ).fetchone()

    assert result["status"] == "ok"
    assert count == 48
    assert latest == date(2022, 12, 31)
    assert metadata == ("月", "指数（2021=100）", source_fcsc.SOURCE_NAME)


def test_update_rejects_a_stale_api_response(tmp_path, monkeypatch):
    raw_csv = tmp_path / "df_cpi_3.2.0.csv"
    raw_csv.write_bytes(_csv_payload())
    monkeypatch.setattr(source_fcsc, "RAW_CSV", raw_csv)

    with duckdb.connect(":memory:") as con:
        db.init_schema(con)
        con.execute(
            "INSERT INTO fcsc_monthly VALUES (?, ?, ?, ?)",
            [date(2023, 1, 31), source_fcsc.INDICATORS["ALL"], 112, "newer.csv"],
        )
        with pytest.raises(ValueError, match="拒绝回退"):
            source_fcsc.update(con, skip_download=True)
