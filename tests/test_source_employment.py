"""Google Trends 解析、入库与工作簿写回。

全部使用 tmp_path 构造的最小样例，不碰网络、不碰真实工作簿。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from htfa.jobs.uae_data import source_employment as se
from htfa.jobs.uae_data import db
from htfa.jobs.uae_data.uae_metadata import complete_metadata
from openpyxl import Workbook, load_workbook


def _timeline_fixture() -> dict:
    return {"default": {"timelineData": [
        {"time": str(int(datetime(2004, month, 1, tzinfo=timezone.utc).timestamp())),
         "value": values}
        for month, values in [(1, [0, 3]), (2, [5, 7]), (3, [9, 0])]
    ]}}


def test_parse_timeline_long_rows() -> None:
    """解析为 long 行：2 关键词×3 月，日期保留原值（日=01）。"""

    rows = se._rows_from_timeline(_timeline_fixture())
    assert len(rows) == 6
    assert {row["keyword"] for row in rows} == {"work in dubai", "work in uae"}
    assert rows[0] == {
        "month": datetime(2004, 1, 1).date(),
        "keyword": "work in dubai",
        "value": 0.0,
    }
    by_key = {(r["month"], r["keyword"]): r["value"] for r in rows}
    assert by_key[(datetime(2004, 2, 1).date(), "work in uae")] == 7.0


def test_parse_timeline_missing_keyword_raises() -> None:
    """列名与预期不符时报错而不是静默。"""

    payload = _timeline_fixture()
    payload["default"]["timelineData"][0]["value"] = [1]
    try:
        se._rows_from_timeline(payload)
    except ValueError as exc:
        assert "2" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for missing column")


def test_parse_google_trends_partial_month_excluded() -> None:
    payload = _timeline_fixture()
    payload["default"]["timelineData"][-1]["isPartial"] = True
    rows = se._rows_from_timeline(payload)
    assert rows[0]["month"] == datetime(2004, 1, 1).date()
    assert rows[-1]["month"] == datetime(2004, 2, 1).date()
    assert len(rows) == 4


def test_update_and_workbook_roundtrip(tmp_path, monkeypatch) -> None:
    """update() 入库 → merge() 写表，保留零值、日期及两条序列。"""

    monkeypatch.setattr(se, "RAW_EMPLOYMENT", tmp_path)
    monkeypatch.setattr(se, "_fetch_google_trends", lambda: (
        se._rows_from_timeline(_timeline_fixture()), "fixture"
    ))
    db_path = tmp_path / "test.duckdb"
    connect = db.connect
    monkeypatch.setattr(db, "connect", lambda *args, **kwargs: connect(db_path, **kwargs))

    con = db.connect(db_path)
    db.init_schema(con)
    outcome = se.update(con)
    assert outcome["status"] == "ok"
    assert outcome["rows"] == 6
    complete_metadata(con)
    con.close()

    target = tmp_path / "workbook.xlsx"
    Workbook().save(target)
    merged = se.merge(target)
    assert merged["status"] == "ok"
    workbook = load_workbook(target, read_only=True, data_only=True)
    rows = list(workbook[se.TARGET_SHEET].iter_rows(min_row=7, values_only=True))
    assert [(row[0].strftime("%Y-%m-%d"), *row[1:]) for row in rows] == [
        ("2004-03-01", 9, 0), ("2004-02-01", 5, 7), ("2004-01-01", 0, 3),
    ]
    workbook.close()


def test_db_holds_exact_month_dates() -> None:
    """DB 中的月份日期与 CSV 原值一致（不改月末/月初）。"""

    rows = [
        {"month": datetime(2004, 1, 1).date(), "keyword": "work in dubai", "value": 0.0},
        {"month": datetime(2004, 1, 1).date(), "keyword": "work in uae", "value": 3.0},
    ]
    con = db.connect(":memory:")
    db.init_schema(con)
    with db.transaction(con):
        db.replace(con, "employment_search_index", rows)
    stored = con.execute(
        "SELECT month, keyword, value FROM employment_search_index ORDER BY keyword"
    ).fetchall()
    assert stored == [
        (datetime(2004, 1, 1).date(), "work in dubai", 0.0),
        (datetime(2004, 1, 1).date(), "work in uae", 3.0),
    ]
    con.close()
