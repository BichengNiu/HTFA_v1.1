"""Source writes must target base tables when main contains same-name views."""

import ast
from datetime import date
from pathlib import Path

from htfa.jobs.uae_data import db, source_emirates_post, source_portwatch


def test_source_writes_qualify_known_detail_tables():
    con = db.connect(":memory:")
    try:
        db.init_schema(con)
        detail_tables = {
            row[0] for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='detail'"
            ).fetchall()
        }
    finally:
        con.close()
    detail_tables.update({"portwatch_uae_daily", "portwatch_chokepoint_daily"})
    source_dir = Path(db.__file__).parent
    for path in source_dir.glob("source_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            function = call.func
            if (
                function.attr not in {"replace", "ensure"}
                or not isinstance(function.value, ast.Name)
                or function.value.id != "db"
                or len(call.args) < 2
                or not isinstance(call.args[1], ast.Constant)
            ):
                continue
            assert call.args[1].value not in detail_tables, (
                f"{path.name}:{call.lineno}: detail-table write lacks schema qualification"
            )


def test_emirates_post_update_writes_detail_table_with_main_view(monkeypatch, tmp_path):
    source = source_emirates_post
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    (tmp_path / source.RAW_FILE_NAME).touch()
    row = {
        "period": date(2025, 12, 31), "origin_city": "Dubai",
        "destn_city": "Abu Dhabi", "service": "Parcel", "volume": 42, "raw_rows": 1,
    }
    monkeypatch.setattr(source, "parse_workbook", lambda path: (
        [row], {}, {"dup_groups": 0},
    ))
    con = db.connect(":memory:")
    try:
        db.init_schema(con)
        con.execute(
            "CREATE VIEW main.emirates_post_monthly AS "
            "SELECT * FROM detail.emirates_post_monthly"
        )
        for _ in range(2):
            assert source.update(con, skip_download=True)["status"] == "ok"
        assert con.execute("SELECT volume FROM detail.emirates_post_monthly").fetchall() == [
            (42,),
        ]
        assert con.execute("SELECT volume FROM main.emirates_post_monthly").fetchall() == [
            (42,),
        ]
    finally:
        con.close()


def test_portwatch_update_writes_both_detail_tables_with_main_views(monkeypatch, tmp_path):
    source = source_portwatch
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    uae_file, choke_file = tmp_path / "uae.csv", tmp_path / "choke.csv"
    for path in (uae_file, choke_file):
        path.touch()
    monkeypatch.setattr(source, "UAE_FILE", uae_file)
    monkeypatch.setattr(source, "CHOKEPOINT_FILE", choke_file)
    uae = {
        "date": date(2026, 9, 30), "portid": "p1", "portname": "Port 1",
        "country": "United Arab Emirates", "iso3": "ARE",
        **{key: 7 for key in source.UAE_VALUE_COLUMNS},
    }
    choke = {
        "date": date(2026, 9, 30), "portid": "chokepoint6", "portname": "Hormuz",
        **{key: 3 for key in source.CHOKEPOINT_VALUE_COLUMNS},
    }
    monkeypatch.setattr(source, "parse_portwatch_csv", lambda path, *a, **k: (
        [uae] if path == uae_file else [choke]
    ))
    con = db.connect(":memory:")
    try:
        db.init_schema(con)
        con.execute(source.UAE_TABLE_DDL)
        con.execute(source.CHOKEPOINT_TABLE_DDL)
        for table in ("portwatch_uae_daily", "portwatch_chokepoint_daily"):
            con.execute(f"CREATE VIEW main.{table} AS SELECT * FROM detail.{table}")
        for _ in range(2):
            assert source.update(con, skip_download=True)["status"] == "ok"
        for table, column, expected in (
            ("portwatch_uae_daily", source.UAE_VALUE_COLUMNS[0], 7),
            ("portwatch_chokepoint_daily", source.CHOKEPOINT_VALUE_COLUMNS[0], 3),
        ):
            assert con.execute(f"SELECT {column} FROM detail.{table}").fetchall() == [(expected,)]
            assert con.execute(f"SELECT {column} FROM main.{table}").fetchall() == [(expected,)]
    finally:
        con.close()
