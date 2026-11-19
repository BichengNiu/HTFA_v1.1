"""Native routing, read-only presentation and publication safety contracts."""

import json
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from htfa.monitoring.energy_supply.jobs import publish, snapshot_update
from htfa.monitoring.uae.jobs import db
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
