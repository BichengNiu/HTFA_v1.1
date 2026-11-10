"""Cold-cache refresh must preserve LFS history, including same-count losses."""

from datetime import date
import json

import duckdb
import pytest

from htfa.jobs.uae_data import db
from htfa.jobs.uae_data.history_validation import validate_history


def make_database(path, periods):
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE observations(period DATE PRIMARY KEY,value DOUBLE,source VARCHAR)")
        for period, value in periods:
            con.execute("INSERT INTO observations VALUES (?,?,?)", [period, value, "original"])


def test_incremental_merge_preserves_uncovered_history_and_provenance():
    with db.connect(":memory:") as con:
        con.execute("CREATE TABLE observations(period DATE PRIMARY KEY,value DOUBLE,source VARCHAR)")
        with db.transaction(con):
            db.merge_observations(con, "observations", [
                {"period": date(2020, 1, 31), "value": 7, "source": "history"},
                {"period": date(2026, 1, 31), "value": 2, "source": "old"},
            ], ("period",))
        with db.transaction(con):
            db.merge_observations(con, "observations", [
                {"period": date(2026, 1, 31), "value": 0, "source": "revision"},
                {"period": date(2026, 2, 28), "value": None, "source": "missing"},
            ], ("period",))
            db.merge_observations(con, "observations", [
                {"period": date(2020, 1, 31), "value": None, "source": "incomplete bulletin"},
            ], ("period",))
        assert con.execute("SELECT * FROM observations ORDER BY period").fetchall() == [
            (date(2020, 1, 31), 7, "history"),
            (date(2026, 1, 31), 0, "revision"),
            (date(2026, 2, 28), None, "missing"),
        ]


@pytest.mark.parametrize("mutation", ["delete", "replace_same_count", "null", "drop"])
def test_history_guard_rejects_loss(tmp_path, mutation):
    before, after = tmp_path / "before.duckdb", tmp_path / "after.duckdb"
    records = [(date(2020, 1, 31), 3), (date(2026, 1, 31), 0)]
    make_database(before, records)
    make_database(after, records)
    with duckdb.connect(str(after)) as con:
        if mutation == "drop":
            con.execute("DROP TABLE observations")
        elif mutation == "null":
            con.execute("UPDATE observations SET value=NULL WHERE value=0")
        else:
            con.execute("DELETE FROM observations WHERE period='2020-01-31'")
            if mutation == "replace_same_count":
                con.execute("INSERT INTO observations VALUES ('2026-02-28',8,'new')")
    with pytest.raises(ValueError, match="removed|erased"):
        validate_history(before, after)


def test_history_guard_allows_revisions_and_additions(tmp_path):
    before, after = tmp_path / "before.duckdb", tmp_path / "after.duckdb"
    make_database(before, [(date(2020, 1, 31), 3)])
    make_database(after, [(date(2020, 1, 31), 0), (date(2026, 1, 31), 7)])
    assert validate_history(before, after)["status"] == "ok"


def test_cbuae_partial_bulletin_keeps_lfs_history(tmp_path, monkeypatch):
    from decimal import Decimal
    from htfa.jobs.uae_data import source_cbuae as source
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    (tmp_path / "2026-01.xlsx").touch()
    observation = source.Observation(
        period="2026-01", values=tuple(Decimal("3") for _ in source.CBUAE_CREDIT_INDICATORS),
        source_period="2026-01", source_file="2026-01.xlsx",
    )
    monkeypatch.setattr(source, "extract_workbook", lambda path: [observation])
    monkeypatch.setattr(source, "extract_payment_rows", lambda path: [])
    with db.connect(":memory:") as con:
        db.init_schema(con)
        con.execute("INSERT INTO cbuae_monthly VALUES (?,?,?,?,?)", [
            date(2020, 1, 31), source.CBUAE_CREDIT_INDICATORS[0][0],
            5, "2020-02", "historic.xlsx",
        ])
        source.update(con, skip_download=True)
        assert con.execute("SELECT value,source_file FROM cbuae_monthly WHERE period='2020-01-31'").fetchone() == (5, "historic.xlsx")
        assert con.execute("SELECT COUNT(*) FROM cbuae_monthly WHERE period='2026-01-31'").fetchone()[0] == len(source.CBUAE_CREDIT_INDICATORS)


def test_foreign_labour_refuses_ytd_gap_on_cold_cache(tmp_path, monkeypatch):
    from openpyxl import Workbook
    from htfa.jobs.uae_data import source_foreign_labour as source
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    folder = tmp_path / "philippines"
    folder.mkdir()
    for month in [1, 3]:
        book = Workbook()
        sheet = book.active
        sheet.title = "Tab 11"
        values = [None] * 12
        values[0], values[3], values[7], values[11] = "UNITED ARAB EMIRATES", month * 10, month * 4, month * 6
        sheet.append(values)
        book.save(folder / f"dmw_2026_{month:02d}.xlsx")
        book.close()
    monkeypatch.setattr(source, "find_uae_row", lambda sheet: list(next(sheet.iter_rows(values_only=True))))
    with pytest.raises(RuntimeError, match="Missing preceding DMW YTD"):
        source.parse_philippines()


def test_report_guard_matches_names_after_column_reordering_and_rejects_loss(tmp_path):
    before, after = tmp_path / "before.duckdb", tmp_path / "after.duckdb"
    for path, columns in [(before, ["甲", "乙"]), (after, ["乙", "甲"])]:
        with duckdb.connect(str(path)) as con:
            con.execute("CREATE SCHEMA report")
            con.execute("CREATE TABLE report.sheets(sheet_index INT,sheet_name VARCHAR,heading VARCHAR,column_count INT)")
            con.execute("CREATE TABLE report.observations(sheet_index INT,column_index INT,period DATE,value DOUBLE)")
            con.execute("INSERT INTO report.sheets VALUES(1,'月度',?,3)", [json.dumps([["source"], ["指标", *columns]])])
            con.execute("INSERT INTO report.observations VALUES(1,1,'2020-01-31',0),(1,2,'2020-01-31',2)")
    assert validate_history(before, after, include_report=True)["report_checked"]
    with duckdb.connect(str(after)) as con:
        con.execute("DELETE FROM report.observations WHERE column_index=1")
    with pytest.raises(ValueError, match="Published historical observations removed"):
        validate_history(before, after, include_report=True)


def test_daily_rolls_back_a_successful_worker_that_deleted_history(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from htfa.jobs.energy_supply import publish
    from htfa.jobs.uae_data import daily_refresh
    directory = tmp_path / "data"
    directory.mkdir()
    database, workbook = directory / "uae.duckdb", directory / "阿联酋.xlsx"
    make_database(database, [(date(2020, 1, 31), 1)])
    workbook.write_bytes(b"original workbook")
    monkeypatch.setattr(daily_refresh, "DATA_DIR", directory)
    monkeypatch.setattr(daily_refresh, "DB_PATH", database)
    monkeypatch.setattr(daily_refresh, "WORKBOOK_PATH", workbook)
    monkeypatch.setattr(publish, "publication_lock", lambda path: nullcontext())
    def corrupted_worker(name, candidate, results_dir):
        assert name == "faulty"
        with duckdb.connect(str(candidate / database.name)) as con:
            con.execute("DELETE FROM observations")
            con.execute("INSERT INTO observations VALUES ('2026-01-31',2,'new')")
        (candidate / workbook.name).write_bytes(b"bad workbook")
        return {"status": "ok"}
    monkeypatch.setattr(daily_refresh, "run_worker", corrupted_worker)
    result = daily_refresh.refresh(tmp_path / "results", sources=["faulty"], collect_energy=False)
    assert result["status"] == "error"
    assert "History keys removed" in result["sources"]["faulty"]["error"]
    assert not result.get("installed")
    assert workbook.read_bytes() == b"original workbook"
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute("SELECT period FROM observations").fetchone()[0] == date(2020, 1, 31)
