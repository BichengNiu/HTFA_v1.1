"""阿联酋数据维护作业的包边界与失败隔离契约。"""

from __future__ import annotations

from types import SimpleNamespace
from contextlib import nullcontext

import pytest

from htfa.jobs.uae_data import db

from htfa.jobs.uae_data import merge_workbook, update_data


def test_update_sources_use_package_imports_and_isolate_failures(monkeypatch) -> None:
    class _Connection:
        def close(self) -> None:
            return None

    connection = _Connection()
    calls: list[str] = []

    monkeypatch.setattr(update_data.db, "connect", lambda: connection)
    monkeypatch.setattr(update_data.db, "init_schema", lambda con: calls.append("schema"))
    monkeypatch.setattr(
        update_data.db,
        "log_run",
        lambda con, name, status, **kwargs: calls.append(f"log:{name}:{status}"),
    )
    monkeypatch.setattr(
        update_data,
        "complete_metadata",
        lambda con: {"indicator_rows": 2, "column_rows": 1},
    )

    def import_source(module_name: str, *, package: str | None = None):
        assert package == "htfa.jobs.uae_data"
        name = module_name.removeprefix(".source_")
        if name == "cbuae":
            def fail(*args, **kwargs):
                raise ValueError("broken")

            return SimpleNamespace(update=fail)
        return SimpleNamespace(update=lambda *args, **kwargs: {"status": "ok", "rows": 3})

    monkeypatch.setattr(update_data.importlib, "import_module", import_source)

    result = update_data.run_sources(["baker_hughes", "cbuae"], skip_download=True)

    assert result["baker_hughes"]["status"] == "ok"
    assert result["cbuae"]["status"] == "failed"
    assert result["_metadata"]["status"] == "ok"
    assert calls == [
        "schema",
        "log:baker_hughes:ok",
        "log:cbuae:failed",
        "log:metadata:ok",
    ]


def test_merge_does_not_sync_dictionary_after_source_failure(monkeypatch, tmp_path) -> None:
    imported: list[str] = []

    def import_source(module_name: str, *, package: str | None = None):
        assert package == "htfa.jobs.uae_data"
        imported.append(module_name)
        if module_name == ".source_cbuae":
            def fail(path):
                raise ValueError("broken")

            return SimpleNamespace(merge=fail)
        return SimpleNamespace(merge=lambda path: {"status": "ok"})

    monkeypatch.setattr(merge_workbook.importlib, "import_module", import_source)
    monkeypatch.setattr(
        merge_workbook,
        "sync_workbook_dictionary",
        lambda path: (_ for _ in ()).throw(AssertionError("dictionary sync must not run")),
    )

    result = merge_workbook.main(
        [
            "--source",
            "baker_hughes,cbuae",
            "--workbook",
            str(tmp_path / "阿联酋.xlsx"),
        ]
    )

    assert result == 1
    assert imported == [".source_baker_hughes", ".source_cbuae"]


@pytest.mark.parametrize("source_status", ["ok", "skipped"])
def test_merge_publishes_once_after_all_sources_and_dictionary(monkeypatch, tmp_path, source_status):
    calls = []

    def import_source(name, *, package=None):
        return SimpleNamespace(merge=lambda path: (
            calls.append(name) or {"status": source_status}
        ))

    monkeypatch.setattr(merge_workbook.importlib, "import_module", import_source)
    monkeypatch.setattr(merge_workbook, "cleanup_excel_automation", lambda: None)
    monkeypatch.setattr(merge_workbook.db, "connect", lambda: nullcontext(object()))
    monkeypatch.setattr(merge_workbook, "sync_workbook_dictionary", lambda path: (
        calls.append("dictionary") or {
            "added": 0, "updated": 0, "removed": 0, "sheet_indicators": 1,
        }
    ))
    monkeypatch.setattr(merge_workbook, "publish_workbook", lambda con, path: (
        calls.append("publish") or {"sheets": 2, "observations": 3, "version": "test"}
    ))

    assert merge_workbook.main([
        "--source", "salik,employment", "--workbook", str(tmp_path / "book.xlsx")
    ]) == 0
    assert calls == [".source_salik", ".source_employment", "dictionary", "publish"]


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
def test_shared_transaction_rolls_back_atomically_and_keeps_connection_open(error_type):
    con = db.connect(":memory:")
    try:
        con.execute("CREATE TABLE first_table (value INTEGER)")
        con.execute("CREATE TABLE second_table (value INTEGER)")
        with pytest.raises(error_type):
            with db.transaction(con):
                con.execute("INSERT INTO first_table VALUES (1)")
                con.execute("INSERT INTO second_table VALUES (2)")
                raise error_type("interrupted")
        assert con.execute("SELECT count(*) FROM first_table").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM second_table").fetchone() == (0,)
        with db.transaction(con):
            con.execute("INSERT INTO first_table VALUES (3)")
        assert con.execute("SELECT value FROM first_table").fetchone() == (3,)
    finally:
        con.close()


@pytest.mark.parametrize("result", [{}, {"status": "unknown"}])
def test_merge_does_not_publish_a_source_without_explicit_success(monkeypatch, tmp_path, result):
    monkeypatch.setattr(merge_workbook, "cleanup_excel_automation", lambda: None)
    monkeypatch.setattr(merge_workbook.importlib, "import_module", lambda *args, **kwargs:
                        SimpleNamespace(merge=lambda path: result))
    monkeypatch.setattr(merge_workbook, "sync_workbook_dictionary", lambda path:
                        pytest.fail("invalid merge must not reach publication"))
    assert merge_workbook.main(["--source", "cbuae", "--workbook", str(tmp_path / "test.xlsx")]) == 1


def test_update_rejects_missing_success_and_always_closes_connection(monkeypatch):
    closed = []
    connection = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(update_data.db, "connect", lambda: connection)
    monkeypatch.setattr(update_data.db, "init_schema", lambda con: None)
    monkeypatch.setattr(update_data.db, "log_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(update_data, "complete_metadata", lambda con: {"indicator_rows": 0, "column_rows": 0})
    monkeypatch.setattr(update_data.importlib, "import_module", lambda *args, **kwargs:
                        SimpleNamespace(update=lambda *args, **kwargs: {"rows": 1}))
    result = update_data.run_sources(["cbuae"])
    assert result["cbuae"]["status"] == "failed"
    assert closed == [True]


def test_update_closes_connection_when_schema_initialization_fails(monkeypatch):
    closed = []
    monkeypatch.setattr(update_data.db, "connect", lambda: SimpleNamespace(close=lambda: closed.append(True)))
    def fail(con):
        raise RuntimeError("bad schema")
    monkeypatch.setattr(update_data.db, "init_schema", fail)
    with pytest.raises(RuntimeError, match="bad schema"):
        update_data.run_sources(["cbuae"])
    assert closed == [True]


def test_source_selection_rejects_an_empty_request():
    with pytest.raises(ValueError, match="At least one"):
        update_data.resolve_source_names(" , ")
    with pytest.raises(ValueError, match="At least one"):
        merge_workbook.resolve_source_names(" , ")


@pytest.mark.parametrize("metadata", [None, {"status": "failed", "note": "metadata invalid"}])
def test_update_main_never_merges_without_successful_metadata(monkeypatch, metadata):
    results = {"cbuae": {"status": "ok", "rows": 1}}
    if metadata is not None:
        results["_metadata"] = metadata
    monkeypatch.setattr(update_data, "run_sources", lambda *args, **kwargs: results)
    monkeypatch.setattr(update_data.importlib, "import_module", lambda *args, **kwargs:
                        pytest.fail("metadata failure must stop the merge"))
    with pytest.raises(KeyError if metadata is None else RuntimeError):
        update_data.main(["--source", "cbuae"])


def test_update_main_merges_the_requested_sources_after_metadata(monkeypatch):
    calls = []
    monkeypatch.setattr(update_data, "run_sources", lambda *args, **kwargs: {
        "cbuae": {"status": "ok", "rows": 1}, "_metadata": {"status": "ok"},
    })
    def import_merge(name, **kwargs):
        assert name == ".merge_workbook"
        return SimpleNamespace(main=lambda args: calls.append(args) or 0)
    monkeypatch.setattr(update_data.importlib, "import_module", import_merge)
    assert update_data.main(["--source", "cbuae"]) == 0
    assert calls == [["--source", "cbuae"]]
