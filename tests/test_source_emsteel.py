"""Coverage, provenance, failure preservation and DB-to-Excel Emsteel contracts."""

import copy
import hashlib
import json
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

from htfa.monitoring.uae.jobs import db, source_emsteel as source


def payload():
    return {
        "items": [dict(id="emsteel-xw", frequency="monthly", currency="AED",
                       vat="excluded", unit_en="tonne", spec_en="10–40 mm, ex-works",
                       basis_en="Monthly mill list price")],
        "observations": [dict(
            item_id="emsteel-xw", period=p, status="published", price=2500,
            source_title="Monthly quotation", source_url="https://example.com/quote",
            extra_source_urls=[], note="",
        ) for p in source.expected_periods("2026-10")],
    }


def no_article(url):
    raise AssertionError(f"Unexpected article fetch: {url}")


def build(data, loader=no_article):
    return source.build_rows(data, loader, today=date(2026, 11, 3))


def test_closed_months_and_coverage():
    data = payload()
    data["observations"].append(dict(data["observations"][-1], period="2026-11"))
    rows = build(data)
    assert len(rows) == 34
    assert rows[0]["period"] == date(2024, 1, 31)
    assert rows[1]["period"] == date(2024, 2, 29)
    assert rows[-1]["period"] == date(2026, 10, 31)


def test_rejects_unverified_gap_and_duplicate_without_forward_fill():
    data = payload()
    data["observations"] = [x for x in data["observations"] if x["period"] != "2024-04"]
    with pytest.raises(ValueError, match="refusing to forward-fill"):
        build(data)
    data = payload()
    data["observations"].append(copy.copy(data["observations"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        build(data)


@pytest.mark.parametrize("price", [None, True, float("nan"), float("inf"), -1, "2500"])
def test_rejects_invalid_prices(price):
    data = payload()
    data["observations"][0]["price"] = price
    with pytest.raises(ValueError):
        build(data)


def test_excluded_observations_and_compilation_flags():
    data = payload()
    data["observations"][0]["note"] = "Mean of sources: 2490, 2510"
    data["observations"][0]["source_title"] = "year inferred 2024"
    data["observations"][-1]["note"] = "Held unchanged; figure carried from prior month"
    data["observations"].append(dict(data["observations"][1], status="excluded", price=1))
    rows = build(data)
    assert rows[0]["quality_flag"] == "compiled_source_mean;year_inferred"
    assert rows[-1]["quality_flag"] == "compiled_rollover"
    assert len(rows) == 34
    assert rows[0]["evidence_urls"] == '["https://example.com/quote"]'


def test_rejects_catalogue_drift():
    data = payload()
    data["items"][0]["currency"] = "USD"
    with pytest.raises(ValueError, match="catalogue/basis"):
        build(data)


def test_gap_derivations_keep_original_currency_and_basis():
    feb = "February-delivery up AED 55/tonne on January to AED 2,735/t ($745) ex-works"
    jan = source.parse_gap("2024-01", feb)
    assert jan["value"] == 2680
    assert jan["original_value"] == 2735
    assert jan["quality_flag"] == "difference_derived"
    apr = source.parse_gap("2025-04", "$722/mt ex-works, for April production. $1 = AED 3.672")
    assert apr["value"] == Decimal("2651.184")
    assert apr["original_value"] == 722
    assert apr["original_currency"] == "USD"
    assert apr["fx_rate"] == Decimal("3.672")
    may = source.parse_gap("2024-05", "Offers at $745/mt (AED 2,735/mt) for May output")
    assert may["quality_flag"] == "basis_inferred"
    with pytest.raises(ValueError, match="period guard"):
        source.parse_gap("2025-04", "March production $722/mt ex-works")
    with pytest.raises(ValueError, match="price is unavailable"):
        source.parse_gap("2025-04", "for April production. Subscribe to read")


def test_html_ignores_script_prices():
    assert source.page_text("<script>AED 123/t</script><p>AED 456/t</p>") == "AED 456/t"


def test_update_failure_preserves_history(tmp_path, monkeypatch):
    raw = json.dumps(payload()).encode()
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    monkeypatch.setattr(source, "_cached", lambda *a, **k: (raw, "quanto.json"))
    con = db.connect(":memory:")
    db.init_schema(con)
    assert source.update(con)["rows"] == 34
    assert con.execute("SELECT count(*) FROM emsteel_monthly").fetchone()[0] == 34
    assert con.execute("SELECT source_sha256 FROM emsteel_monthly LIMIT 1").fetchone()[0] == hashlib.sha256(raw).hexdigest()
    data = payload()
    data["observations"] = data["observations"][:-1]
    raw = json.dumps(data).encode()
    with pytest.raises(ValueError, match="regressed"):
        source.update(con)
    assert con.execute("SELECT max(period) FROM emsteel_monthly").fetchone()[0] == date(2026, 10, 31)
    con.close()


def test_merge_reads_database_values_and_provenance(tmp_path, monkeypatch):
    path = tmp_path / "test.duckdb"
    con = db.connect(path)
    db.init_schema(con)
    raw = json.dumps(payload()).encode()
    monkeypatch.setattr(source, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(source, "_cached", lambda *a, **k: (raw, "quanto.json"))
    source.update(con)
    # Prove the workbook values come from DB, not the raw payload or a constant.
    con.execute("UPDATE emsteel_monthly SET value=2222.125 WHERE period='2024-01-31'")
    con.close()
    connect = db.connect
    monkeypatch.setattr(db, "connect", lambda _database=None, **kwargs: connect(path, **kwargs))
    book_path = tmp_path / "book.xlsx"
    book = Workbook()
    book.active.title = "指标字典"
    book.active.append(["指标名称", "类型", "行业", "频率", "开始日期", "最新日期", "缺失期数", "数据来源", "预测变量"])
    book.create_sheet("用户数据")["A1"] = "保留"
    book.save(book_path)
    book.close()
    assert source.merge(book_path)["rows"] == 34
    book = load_workbook(book_path)
    sheet = book[source.TARGET_SHEET]
    assert sheet.max_row == 40
    assert sheet.cell(40, 2).value == 2222.125
    assert "https://quantohq.com" in sheet.cell(40, 2).comment.text
    assert "compiled_reported" in sheet.cell(40, 2).comment.text
    assert book["用户数据"]["A1"].value == "保留"
    assert book["指标字典"].cell(2, 1).value == source.INDICATOR
    book.close()
    assert not list(tmp_path.glob(".emsteel-*.xlsx"))
