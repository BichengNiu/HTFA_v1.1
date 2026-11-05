"""source_dld 周度指标纯函数测试。

验证交易下载、完整期间、报告计数和来源契约，不触碰真实 DuckDB 库、
网络下载或 Excel 工作簿（符合模块约定与 pip 环境约束）。
"""

from datetime import date
import csv
import gzip
import json

import duckdb
import pytest

from htfa.jobs.uae_data import source_dld as dld  # noqa: E402


def _write_bulk_archive(path, columns, rows):
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def test_download_only_fetches_consumed_transactions_and_preserves_raw_rows(
    tmp_path, monkeypatch,
):
    columns = ["transaction_id", "instance_date", "load_timestamp"]
    rows = [["1", "1899-01-01", "2026-09-01"],
            ["2", "not a date", "2026-09-02"],
            ["3", "2026-08-31", "2026-09-03"]]
    first, second = tmp_path / "first.csv.gz", tmp_path / "second.csv.gz"
    _write_bulk_archive(first, columns, rows[:2])
    _write_bulk_archive(second, columns, rows[2:])
    # Existing local archives are user assets, even when no longer refreshed.
    legacy = tmp_path / "DLD_Land_Registry_ALL.csv"
    legacy.write_text("keep existing raw data", encoding="utf-8")
    requested = []

    def resolve(dataset_id, page):
        requested.append(dataset_id)
        return [first, second]

    monkeypatch.setattr(dld, "RAW_DLD_DIR", tmp_path)
    monkeypatch.setattr(dld, "_get_bulk_csv_files", resolve)
    monkeypatch.setattr(dld, "_fetch_and_stage", lambda files, folder: (files, []))
    dld._download_all()

    assert requested == [dld.TRANSACTIONS_DATASET_ID]
    with (tmp_path / "DLD_Transactions_ALL.csv").open(encoding="utf-8-sig", newline="") as stream:
        actual = csv.reader(stream)
        assert list(actual) == [columns, *rows]
    manifest = json.loads((tmp_path / "DLD_download_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["output_files"]) == {"transactions"}
    assert manifest["transactions_rows"] == 3
    assert manifest["dates_before_1900_rows"] == 1
    assert manifest["unparseable_date_rows"] == 1
    assert manifest["from_date_since_1900"] == "2026-08-31"
    assert legacy.read_text(encoding="utf-8") == "keep existing raw data"


def test_bulk_schema_failure_preserves_previous_complete_transaction_file(tmp_path):
    first, second = tmp_path / "first.csv.gz", tmp_path / "second.csv.gz"
    _write_bulk_archive(first, ["transaction_id"], [["1"]])
    _write_bulk_archive(second, ["different_schema"], [["2"]])
    target = tmp_path / "transactions.csv"
    target.write_bytes(b"previous complete data")
    with pytest.raises(RuntimeError, match="schema mismatch"):
        dld._merge_transactions([first, second], target)
    assert target.read_bytes() == b"previous complete data"
    assert not target.with_suffix(".csv.part").exists()


# ---------------------------------------------------------------------------
# 纯函数基础
# ---------------------------------------------------------------------------

def test_numeric_value_requires_duckdb_numeric_type() -> None:
    assert dld._numeric_value(None, column="value") is None
    assert dld._numeric_value(7, column="value") == 7.0
    assert dld._numeric_value(2.25, column="value") == 2.25
    with pytest.raises(TypeError, match="DuckDB column 'value'"):
        dld._numeric_value("12.5", column="value")


# ---------------------------------------------------------------------------
# build_rows 行为
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 入库映射 / 常量契约
# ---------------------------------------------------------------------------


def test_raw_weekly_sql_targets_unified_schema() -> None:
    assert "detail.dld_transactions" in dld.RAW_WEEKLY_SQL
    assert "FROM transactions" not in dld.RAW_WEEKLY_SQL
    assert "FROM detail.dld_transactions" in dld.RAW_WEEKLY_SQL


def test_build_sales_monthly_ignores_partial_latest_month() -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE SCHEMA detail")
        con.execute(
            """
            CREATE TABLE detail.dld_transactions (
                instance_date DATE,
                property_usage_en VARCHAR,
                reg_type_en VARCHAR,
                trans_group_en VARCHAR,
                actual_worth DOUBLE
            )
            """
        )
        con.executemany(
            "INSERT INTO detail.dld_transactions VALUES (?, ?, ?, ?, ?)",
            [
                (
                    date(2026, 7, 31),
                    "Residential",
                    "Existing Properties",
                    "Sales",
                    100.0,
                ),
                (
                    date(2026, 8, 10),
                    "Residential",
                    "Existing Properties",
                    "Sales",
                    200.0,
                ),
            ],
        )

        rows = dld.build_sales_monthly(con)

        assert {row["period"] for row in rows} == {date(2026, 7, 31)}
        assert rows[0]["value_aed"] == 100.0
    finally:
        con.close()


def test_online_snapshot_change_rebuilds_existing_dld_base(tmp_path, monkeypatch) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE SCHEMA detail")
        con.execute("CREATE SCHEMA dld")
        con.execute("CREATE TABLE detail.dld_transactions (instance_date DATE)")
        txn_csv = tmp_path / "DLD_Transactions_ALL.csv"
        txn_csv.write_text("placeholder", encoding="utf-8")
        manifest = tmp_path / "DLD_download_manifest.json"
        manifest.write_text(
            '{"transaction_source_files": [{"file_name": "old.csv.gz"}]}',
            encoding="utf-8",
        )
        monkeypatch.setattr(dld, "RAW_DLD_DIR", tmp_path)
        monkeypatch.setattr(
            dld,
            "_get_bulk_csv_files",
            lambda *_args: [{"file_name": "new.csv.gz"}],
        )
        monkeypatch.setattr(dld, "_build_base_from_csv", lambda _con: "rebuilt")
        downloaded = []
        monkeypatch.setattr(dld, "_download_all", lambda: downloaded.append(True))

        note = dld._ensure_base_tables(con, force=False, skip_download=False)

        assert downloaded == [True]
        assert "rebuilt" in note
    finally:
        con.close()


def test_download_metadata_retries_invalid_200_json(monkeypatch):
    responses = iter([
        "Liferay.authToken = 'public-test-token'",
        "<html>temporary gateway response</html>",
        json.dumps({"success": True, "data": {"metadata": [{"files": [
            {"file_name": "latest.csv.gz", "file_extension": "csv", "file_url": "https://example.test/data"}
        ]}]}}),
    ])
    monkeypatch.setattr(dld, "_http_read", lambda *a, **kw: next(responses))
    monkeypatch.setattr(dld.time, "sleep", lambda delay: None)
    assert dld._get_bulk_csv_files("123", "https://example.test/page")[0]["file_name"] == "latest.csv.gz"


def test_download_metadata_rejects_persistent_invalid_json(monkeypatch):
    responses = iter(["Liferay.authToken = 'public-test-token'", "", "", ""])
    monkeypatch.setattr(dld, "_http_read", lambda *a, **kw: next(responses))
    monkeypatch.setattr(dld.time, "sleep", lambda delay: None)
    with pytest.raises(RuntimeError, match="invalid JSON after 3 attempts"):
        dld._get_bulk_csv_files("123", "https://example.test/page")


def test_column_dictionary_contract() -> None:
    assert len(dld.COLUMN_DICTIONARY) == len(dld.KEEP_COLUMNS) == 9
    assert all(len(row) == 7 for row in dld.COLUMN_DICTIONARY)
    object_names = {row[0] for row in dld.COLUMN_DICTIONARY}
    # 2026-08 瘦身：只保留 transactions（land_registry 已不再入库）
    assert object_names == {"detail.dld_transactions"}
    assert {row[1] for row in dld.COLUMN_DICTIONARY} == set(dld.KEEP_COLUMNS)


def test_column_dictionary_matches_current_metadata_rows() -> None:
    # meta_column_dictionary 应只含与内置常量一致的保留列。
    by_object: dict[str, dict[str, tuple]] = {}
    for row in dld.COLUMN_DICTIONARY:
        by_object.setdefault(row[0], {})[row[1]] = row
    assert set(by_object["detail.dld_transactions"]) == set(dld.KEEP_COLUMNS)
    assert "dld.land_registry" not in by_object
    assert by_object["detail.dld_transactions"]["transaction_id"][2] == "VARCHAR"
