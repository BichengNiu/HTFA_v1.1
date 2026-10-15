"""FCSC UAE.Stat CPI ingestion and database contract."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from math import prod

import duckdb
import pytest

from htfa.jobs.uae_data import db, source_fcsc


def _csv_payload(
    *, months: int = 66, duplicate: bool = False, missing_last_fnb: bool = False,
) -> bytes:
    records = [
        "STRUCTURE,STRUCTURE_ID,ACTION,MEASURE,UNIT_MEASURE,REF_AREA,FREQ,"
        "CPI_DIV,SOURCE_DETAIL,TIME_PERIOD,OBS_VALUE,DECIMALS,OBS_STATUS,UNIT_MULT,BASE_YEAR"
    ]
    indices = {"ALL": {}, "FNB": {}}
    new_monthly_rates = {
        "ALL": (0.34, 0.09, 1.31, 1.74, 0.58, 0.41),
        "FNB": (0.18, -1.84, 4.56, 1.74, 0.40, 1.70),
    }
    year, month = 2021, 1
    for index in range(months):
        period = f"{year:04d}-{month:02d}"
        base_year = "2021" if (year, month) <= (2025, 12) else "2024"
        for division, value in (("ALL", 100 + index * 0.2), ("FNB", 100 + index * 0.3)):
            if missing_last_fnb and division == "FNB" and index == months - 1:
                continue
            if base_year == "2024":
                value = 103 + (month - 1) * 0.2 + (0.4 if division == "FNB" else 0)
            indices[division][period] = value
            records.append(
                f"DATA,FCSA:DF_CPI(3.3.0),I,CPI_INDEX,INDX,AE,M,{division},"
                f"FCSC,{period},{value:.2f},2,,,{base_year}"
            )
            if year >= 2023 and base_year == "2021":
                previous_period = f"{year - 1:04d}-{month:02d}"
                previous_value = indices[division][previous_period]
                yoy_value = round((value / previous_value - 1) * 100, 2)
                if period == "2023-01":
                    yoy_value = 2.35 if division == "ALL" else 3.48
                records.append(
                    f"DATA,FCSA:DF_CPI(3.3.0),I,CPI_YINFL,PERCENT,AE,M,{division},"
                    f"FCSC,{period},{yoy_value:.2f},2,,,{base_year}"
                )
            if year >= 2023:
                if base_year == "2024":
                    rate = new_monthly_rates[division][month - 1]
                else:
                    rate = 0.2 if division == "ALL" else 0.3
                records.append(
                    f"DATA,FCSA:DF_CPI(3.3.0),I,CPI_MINFL,PERCENT,AE,M,{division},"
                    f"FCSC,{period},{rate:.2f},2,,,{base_year}"
                )
        if duplicate and index == 0:
            records.append(
                f"DATA,FCSA:DF_CPI(3.3.0),I,CPI_INDEX,INDX,AE,M,ALL,"
                f"FCSC,{period},100,2,,,2021"
            )
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    # Published annual rates are used where available; 2022 is derived from index levels.
    records.append(
        "DATA,FCSA:DF_CPI(3.2.0),I,CPI_ANNCHG21,PERCENT,AE,M,ALL,"
        "FCSA,2023-01,2.35,2,,"
    )
    records.append(
        "DATA,FCSA:DF_CPI(3.2.0),I,CPI_ANNCHG21,PERCENT,AE,M,FNB,"
        "FCSA,2023-01,3.48,2,,"
    )
    return ("\n".join(records) + "\n").encode("utf-8")


def test_parse_cpi_csv_filters_national_monthly_index_levels():
    rows = source_fcsc.parse_cpi_csv(_csv_payload())
    assert len(rows) == 132
    assert rows[0] == {
        "period": date(2021, 1, monthrange(2021, 1)[1]),
        "indicator": source_fcsc.INDEX_INDICATORS["ALL"],
        "value": 100.0,
        "base_year": "2021",
        "source_file": source_fcsc.RAW_CSV.name,
    }
    assert rows[-1]["indicator"] == source_fcsc.INDEX_INDICATORS["FNB"]
    assert rows[-1]["period"] == date(2026, 6, 30)
    assert rows[-1]["base_year"] == "2024"


def test_parse_rejects_duplicate_or_incomplete_series():
    with pytest.raises(ValueError, match="重复观测"):
        source_fcsc.parse_cpi_csv(_csv_payload(duplicate=True))
    incomplete = _csv_payload(missing_last_fnb=True)
    with pytest.raises(ValueError, match="期间不一致"):
        source_fcsc.parse_cpi_csv(incomplete)


def test_update_writes_duckdb_and_dictionary_from_cached_official_csv(tmp_path, monkeypatch):
    raw_csv = tmp_path / "df_cpi_3.3.0.csv"
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
        jan_2022 = con.execute(
            "SELECT value FROM fcsc_monthly WHERE period = ? AND indicator = ?",
            [date(2022, 1, 31), source_fcsc.INDICATORS["ALL"]],
        ).fetchone()[0]
        jan_2023 = con.execute(
            "SELECT value FROM fcsc_monthly WHERE period = ? AND indicator = ?",
            [date(2023, 1, 31), source_fcsc.INDICATORS["ALL"]],
        ).fetchone()[0]
        jun_2026 = con.execute(
            "SELECT value FROM fcsc_monthly WHERE period = ? AND indicator = ?",
            [date(2026, 6, 30), source_fcsc.INDICATORS["ALL"]],
        ).fetchone()[0]

    assert result["status"] == "ok"
    assert count == 108
    assert latest == date(2026, 6, 30)
    assert metadata == ("月", "%", source_fcsc.SOURCE_NAME)
    assert float(jan_2022) == pytest.approx(2.4)
    assert float(jan_2023) == pytest.approx(2.35)
    expected_jun_2026 = round(
        (prod(
            1 + rate / 100
            for rate in (0.2,) * 6 + (0.34, 0.09, 1.31, 1.74, 0.58, 0.41)
        ) - 1) * 100,
        2,
    )
    assert float(jun_2026) == pytest.approx(expected_jun_2026)


def test_update_rejects_a_stale_api_response(tmp_path, monkeypatch):
    raw_csv = tmp_path / "df_cpi_3.3.0.csv"
    raw_csv.write_bytes(_csv_payload())
    monkeypatch.setattr(source_fcsc, "RAW_CSV", raw_csv)

    with duckdb.connect(":memory:") as con:
        db.init_schema(con)
        con.execute(
            "INSERT INTO fcsc_monthly VALUES (?, ?, ?, ?)",
            [date(2026, 7, 31), source_fcsc.INDICATORS["ALL"], 3.2, "newer.csv"],
        )
        with pytest.raises(ValueError, match="拒绝回退"):
            source_fcsc.update(con, skip_download=True)
