"""阿联酋数据维护作业的包边界与失败隔离契约。"""

from __future__ import annotations

from types import SimpleNamespace

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
