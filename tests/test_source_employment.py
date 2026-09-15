"""Tests for data/source_employment.py：CSV 解析、入库往返、宽表导出。

全部使用 tmp_path 构造的最小样例，不碰网络、不碰真实工作簿。
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from htfa.jobs.uae_data import source_employment as se
from htfa.jobs.uae_data import db


def _write_fixture(path: Path) -> Path:
    """最小样例：3 个月 × 2 关键词 + 1 列无关字段（visa uae）。"""

    lines = [
        '"Time","work in dubai","work in uae","visa uae"',
        '"2004-01-01",0,3,18',
        '"2004-02-01",5,7,36',
        '"2004-03-01",9,0,40',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_parse_csv_long_rows(tmp_path) -> None:
    """解析为 long 行：2 关键词×3 月，日期保留原值（日=01）。"""

    src = _write_fixture(tmp_path / "工作搜索热度.csv")
    rows = se.parse_csv(src)
    assert len(rows) == 6
    assert {row["keyword"] for row in rows} == {"work in dubai", "work in uae"}
    assert rows[0] == {
        "month": datetime(2004, 1, 1).date(),
        "keyword": "work in dubai",
        "value": 0.0,
    }
    by_key = {(r["month"], r["keyword"]): r["value"] for r in rows}
    assert by_key[(datetime(2004, 2, 1).date(), "work in uae")] == 7.0


def test_parse_csv_missing_column_raises(tmp_path) -> None:
    """列名与预期不符时报错而不是静默。"""

    src = tmp_path / "bad.csv"
    src.write_text('"Time","work in dubai"\n"2004-01-01",1\n', encoding="utf-8")
    try:
        se.parse_csv(src)
    except ValueError as exc:
        assert "work in uae" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for missing column")


def test_parse_google_trends_export(tmp_path) -> None:
    """兼容 Google Trends 的空首列表头和 Mon-YY 月份格式。"""

    src = tmp_path / "google-trends.csv"
    src.write_text(
        ",work in dubai,work in uae\nJan-04,0,3\nAug-26,83,69\n",
        encoding="utf-8",
    )
    rows = se.parse_csv(src)
    assert rows[0]["month"] == datetime(2004, 1, 1).date()
    assert rows[-1]["month"] == datetime(2026, 8, 1).date()
    assert rows[-1]["value"] == 69.0


def test_update_and_export_roundtrip(tmp_path, monkeypatch) -> None:
    """update() 入库 → merge() 宽表导出：数值、日期、列名完全往返。"""

    src = _write_fixture(tmp_path / "工作搜索热度.csv")
    monkeypatch.setattr(se, "RAW_EMPLOYMENT", tmp_path)
    export_target = tmp_path / "export.csv"
    monkeypatch.setattr(se, "EXPORT_PATH", export_target)
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setattr(se, "connect", lambda *args, **kwargs: db.connect(db_path, **kwargs))

    con = db.connect(db_path)
    db.init_schema(con)
    outcome = se.update(con)
    assert outcome["status"] == "ok"
    assert outcome["rows"] == 6
    con.close()

    merged = se.merge(Path("ignored.xlsx"))  # 参数仅为兼容统一签名
    assert merged["status"] == "ok"
    assert export_target.exists()

    with open(export_target, encoding="utf-8") as source:
        rows = list(csv.reader(source))
    assert rows[0] == ["Time", "work in dubai", "work in uae"]
    assert rows[1] == ["2004-01-01", "0", "3"]
    assert rows[2] == ["2004-02-01", "5", "7"]
    assert rows[3] == ["2004-03-01", "9", "0"]
    assert len(rows) == 4  # 不含 "visa uae" 列


def test_db_holds_exact_month_dates() -> None:
    """DB 中的月份日期与 CSV 原值一致（不改月末/月初）。"""

    rows = [
        {"month": datetime(2004, 1, 1).date(), "keyword": "work in dubai", "value": 0.0},
        {"month": datetime(2004, 1, 1).date(), "keyword": "work in uae", "value": 3.0},
    ]
    con = db.connect(":memory:")
    db.init_schema(con)
    with se._transaction(con):
        db.replace(con, "employment_search_index", rows)
    stored = con.execute(
        "SELECT month, keyword, value FROM employment_search_index ORDER BY keyword"
    ).fetchall()
    assert stored == [
        (datetime(2004, 1, 1).date(), "work in dubai", 0.0),
        (datetime(2004, 1, 1).date(), "work in uae", 3.0),
    ]
    con.close()
