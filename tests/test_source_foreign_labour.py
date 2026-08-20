"""Tests for ``data/source_foreign_labour.py``（DuckDB 入库版）。"""

import sys
from datetime import date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "UAE" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
import source_foreign_labour as source  # noqa: E402


def _make_bangladesh(year: int, month: int, value: int) -> None:
    path = source.RAW_DIR / "bangladesh" / f"bangladesh_bmet_{year}_{month:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            '{"payload": {"totalEmployee": %d, "data": ['
            '{"country_name": "UNITED ARAB EMIRATES", '
            '"total_employee": %d}]}}'
        )
        % (value, value),
        encoding="utf-8",
    )


def test_numeric_handles_dash_and_commas() -> None:
    assert source.numeric(None) == 0
    assert source.numeric("-") == 0
    assert source.numeric("1,234") == 1234


def test_style_sheet_uses_workbook_metadata_protocol() -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    source.style_sheet(
        worksheet,
        [
            {
                "date": date(2026, 7, 31),
                "philippines_total": 10,
                "philippines_new_hires": 4,
                "philippines_rehires": 6,
                "nepal_with_reentry": 20,
                "nepal_without_reentry": 18,
                "bangladesh_clearance": 30,
                "proxy_sum": 60,
                "proxy_index": 1.0,
            }
        ],
    )

    assert [worksheet.cell(row, 1).value for row in range(2, 7)] == [
        "指标名称",
        "频率",
        "单位",
        "来源",
        "更新时间",
    ]


def test_parse_bangladesh_reads_complete_months(tmp_path, monkeypatch) -> None:
    raw_dir = tmp_path / "foreign_labour"
    monkeypatch.setattr(source, "RAW_DIR", raw_dir)
    _make_bangladesh(2026, 6, 100)
    _make_bangladesh(2026, 7, 120)

    monthly = source.parse_bangladesh()

    assert monthly == {"2026-06": 100, "2026-07": 120}


def test_rows_to_long_keeps_only_non_null(tmp_path, monkeypatch) -> None:
    raw_dir = tmp_path / "foreign_labour"
    monkeypatch.setattr(source, "RAW_DIR", raw_dir)
    _make_bangladesh(2026, 6, 100)
    rows = [
        {
            "date": date(2026, 6, 30),
            "philippines_total": None,
            "philippines_new_hires": None,
            "philippines_rehires": None,
            "nepal_with_reentry": None,
            "nepal_without_reentry": None,
            "bangladesh_clearance": 100,
            "proxy_sum": None,
            "proxy_index": None,
            "source_count": 1,
            "quality_flag": "DMW官方YTD较上月回落，无法可靠差分",
        }
    ]
    long_rows = source._rows_to_long(rows)
    assert len(long_rows) == 3  # bangladesh_clearance + source_count + quality_flag 行
    assert long_rows[0]["period"] == date(2026, 6, 30)
    assert long_rows[0]["series"] == "bangladesh_clearance"
    flag_row = [row for row in long_rows if row["series"] == "quality_flag"]
    assert len(flag_row) == 1
    assert flag_row[0]["quality_flag"] == "DMW官方YTD较上月回落，无法可靠差分"


def test_update_roundtrip_with_single_source(tmp_path, monkeypatch) -> None:
    raw_dir = tmp_path / "foreign_labour"
    monkeypatch.setattr(source, "RAW_DIR", raw_dir)
    monkeypatch.setattr(source, "MANIFEST_PATH", raw_dir / "manifest.json")
    _make_bangladesh(2026, 6, 100)
    # 单一国家数据不足 6 个共同基线月，monkeypatch build_rows 走固定输入
    fixed_rows = [
        {
            "date": date(2026, 6, 30),
            "philippines_total": 100,
            "philippines_new_hires": 80,
            "philippines_rehires": 20,
            "nepal_with_reentry": 50,
            "nepal_without_reentry": 30,
            "bangladesh_clearance": 100,
            "proxy_sum": 250,
            "proxy_index": 101.5,
            "source_count": 3,
            "quality_flag": None,
        }
    ]
    monkeypatch.setattr(source, "build_rows", lambda: fixed_rows)

    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = source.update(con, skip_download=True)

    assert outcome["status"] == "ok"
    assert outcome["rows"] == 9
    rows = con.execute(
        "SELECT period, series, value FROM foreign_labour_monthly"
    ).fetchall()
    assert (date(2026, 6, 30), "bangladesh_clearance", 100.0) in rows
    assert (date(2026, 6, 30), "proxy_sum", 250.0) in rows
    con.close()


def test_rows_from_db_roundtrip(tmp_path, monkeypatch) -> None:
    raw_dir = tmp_path / "foreign_labour"
    monkeypatch.setattr(source, "RAW_DIR", raw_dir)
    _make_bangladesh(2026, 6, 100)
    fixed_rows = [
        {
            "date": date(2026, 6, 30),
            "philippines_total": None,
            "philippines_new_hires": None,
            "philippines_rehires": None,
            "nepal_with_reentry": None,
            "nepal_without_reentry": None,
            "bangladesh_clearance": 100,
            "proxy_sum": None,
            "proxy_index": None,
            "source_count": 1,
            "quality_flag": "DMW官方YTD较上月回落，无法可靠差分",
        }
    ]
    monkeypatch.setattr(source, "build_rows", lambda: fixed_rows)

    con = db.connect(":memory:")
    db.init_schema(con)
    rows = source.build_rows()
    long_rows = source._rows_to_long(rows)
    db.replace(con, "foreign_labour_monthly", long_rows)

    restored = source._rows_from_db(con)
    con.close()
    assert restored[0]["date"] == date(2026, 6, 30)
    assert restored[0]["bangladesh_clearance"] == 100
    assert restored[0]["source_count"] == 1
    assert restored[0]["proxy_sum"] is None
    assert restored[0]["quality_flag"] == "DMW官方YTD较上月回落，无法可靠差分"
