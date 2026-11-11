"""Native routing, read-only presentation and publication safety contracts."""

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest
from openpyxl import Workbook, load_workbook
from streamlit.testing.v1 import AppTest

from htfa.monitoring.energy_supply.jobs import publish, snapshot_update
from htfa.monitoring.uae.jobs import db, source_energy_supply
from htfa.monitoring.uae.jobs.paths import DB_PATH
import htfa.monitoring.energy_supply.data.storage as data_store
import htfa.monitoring.energy_supply.processing.ais as ais

APP = Path(__file__).resolve().parents[3] / "app.py"


def test_native_navigation_tabs_and_return_preserve_other_modules():
    before = DB_PATH.stat().st_mtime_ns
    app = AppTest.from_file(APP, default_timeout=90).run()
    assert not app.exception
    next(b for b in app.sidebar.button if b.label == "能源保供").click().run()
    assert not app.exception
    assert not app.error
    assert [tab.label for tab in app.tabs] == ["地图", "港口", "船舶", "油气"]
    assert not app.get("file_uploader")
    assert app.get("iframe") or app.get("component_instance")
    for label in ("港口", "船舶", "油气"):
        app.session_state["energy_supply_main_tabs"] = label
        app.run()
        assert not app.exception
        assert not app.error
        assert app.get("dataframe")
        if label == "港口":
            assert not app.expander
            assert "生成下载数据" not in [button.label for button in app.button]
    next(b for b in app.sidebar.button if b.label == "阿联酋").click().run()
    assert not app.exception
    assert not app.error
    assert [t.label for t in app.tabs] == ["年度数据", "季度数据", "行业分析", "月度数据"]
    assert DB_PATH.stat().st_mtime_ns == before


def test_page_database_connection_rejects_writes():
    with data_store.connect() as con:
        with pytest.raises(duckdb.Error, match="read-only"):
            con.execute("CREATE TABLE energy_supply.forbidden (x INTEGER)")


def test_ais_worker_threads_inherit_the_maintenance_database(tmp_path):
    from io import BytesIO

    database = tmp_path / "threaded.duckdb"
    with data_store.job_database(database):
        with patch("htfa.monitoring.energy_supply.data.openwaters_client.urlopen", side_effect=lambda *args, **kwargs:
                          BytesIO(b'{"type":"FeatureCollection","features":[]}')):
            result = ais.openwaters_snapshot()
        assert result["error"] is None
        assert result["successful_groups"] == result["requested_groups"]
        with data_store.connect() as con:
            assert con.execute("SELECT count(*) FROM source_queries").fetchone()[0] == result["requested_groups"]


def test_monthly_observed_series_and_workbook_preserve_missing_and_zero(tmp_path):
    database = tmp_path / "test.duckdb"
    with data_store.job_database(database):
        with data_store.connect() as con:
            con.execute("INSERT INTO catalogs VALUES ('ports','port1',?,current_timestamp)",
                        [json.dumps({"portid": "port1", "name": "Test port"})])
            for day, value in ((date(2026, 1, 1), 0), (date(2026, 1, 3), None)):
                payload = {"portcalls": value, "import": 0, "export": 2}
                con.execute("INSERT INTO portwatch_daily VALUES ('ports','port1',?,?,?,current_timestamp)",
                            [day, json.dumps(payload), "https://example.org/source"])
    with db.connect(database) as con:
        db.init_schema(con)
        source_energy_supply.update(con, skip_download=True)
        values = con.execute("SELECT indicator,value FROM energy_supply.report_indicators").fetchall()
    imports = [(name, value) for name, value in values if ":进口估算货量:" in name]
    calls = [(name, value) for name, value in values if ":进港次数:" in name]
    assert imports[0][1] == 0
    assert calls[0][1] is None
    workbook = tmp_path / "report.xlsx"
    book = Workbook()
    book.active.title = "existing"
    book.active["A1"] = "preserved"
    book.save(workbook)
    source_energy_supply.merge(workbook, database=database)
    book = load_workbook(workbook)
    try:
        assert book["existing"]["A1"].value == "preserved"
        sheet = book[source_energy_supply.SHEETS["ports"]]
        columns = {cell.value: cell.column for cell in sheet[2]}
        assert sheet.cell(7, columns[imports[0][0]]).value == 0
        assert sheet.cell(7, columns[calls[0][0]]).value is None
    finally:
        book.close()


def test_invalid_source_value_rolls_back_indicator_publication(tmp_path):
    database = tmp_path / "invalid.duckdb"
    with data_store.job_database(database):
        with data_store.connect() as con:
            con.execute("INSERT INTO catalogs VALUES ('ports','p',?,current_timestamp)",
                        [json.dumps({"name": "test"})])
            con.execute("INSERT INTO portwatch_daily VALUES ('ports','p','2026-01-01',?,'source',current_timestamp)",
                        [json.dumps({"portcalls": -1})])
    with db.connect(database) as con:
        db.init_schema(con)
        with pytest.raises(ValueError, match="非法能源观测值"):
            source_energy_supply.update(con)
        assert not con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='report_indicators'").fetchone()[0]


def test_failed_source_restores_entire_candidate(tmp_path):
    candidate = tmp_path / "candidate.duckdb"
    with duckdb.connect(str(candidate)) as con:
        con.execute("CREATE TABLE facts (value INTEGER)")
        con.execute("INSERT INTO facts VALUES (7)")
    with pytest.raises(RuntimeError):
        with snapshot_update.source_checkpoint(candidate):
            with duckdb.connect(str(candidate)) as con:
                con.execute("UPDATE facts SET value=99")
            raise RuntimeError("source failed")
    with duckdb.connect(str(candidate)) as con:
        assert con.execute("SELECT value FROM facts").fetchone()[0] == 7


def test_failed_workbook_replacement_restores_database(tmp_path):
    database, workbook = tmp_path / "db", tmp_path / "book"
    candidate_db, candidate_workbook = tmp_path / "next_db", tmp_path / "next_book"
    database.write_bytes(b"old database")
    workbook.write_bytes(b"old workbook")
    candidate_db.write_bytes(b"new database")
    candidate_workbook.write_bytes(b"new workbook")
    replace = publish.os.replace

    def fail_workbook(source, destination):
        if Path(source) == candidate_workbook:
            raise OSError("workbook locked")
        return replace(source, destination)

    with patch.object(publish.os, "replace", side_effect=fail_workbook):
        with pytest.raises(OSError):
            publish.install_pair(candidate_db, candidate_workbook, database, workbook)
    assert database.read_bytes() == b"old database"
    assert workbook.read_bytes() == b"old workbook"
