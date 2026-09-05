"""Tests for ``data/source_steel.py``（DuckDB 入库版）。"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from htfa.jobs.uae_data import db  # noqa: E402
from htfa.jobs.uae_data import source_steel as source  # noqa: E402


def _payload() -> dict:
    # 旧口径：payload 必须包含全部 15 个产品记录且有报价（目录校验严格），
    # 否则 unknown/missing 会直接报错。
    data = []
    for index, product in enumerate(source.PRODUCTS):
        if index == 0:  # 钢坯及方坯：区间报价 + 8 月新价
            prices = {"2026-07-01": "600-620", "2026-08-01": "630"}
        elif index == 4:  # 线材：8 月缺报
            prices = {"2026-07-01": "680", "2026-08-01": None}
        else:
            prices = {"2026-07-01": "600"}
        data.append({"product": product.english, "origin": "-", "prices": prices})
    return {
        "dates": ["2026-07-01", "2026-08-01"],
        "data": data,
    }


def test_parse_quote_range_and_scalar() -> None:
    assert source.parse_quote("600-620") == (600.0, 620.0, 610.0)
    assert source.parse_quote("630") == (630.0, 630.0, 630.0)
    with pytest.raises(ValueError, match="descending bounds"):
        source.parse_quote("700-600")


def test_month_end_maps_first_of_month_to_last_day() -> None:
    assert source.month_end("2026-08-01") == date(2026, 8, 31)
    assert source.month_end("2026-02-01") == date(2026, 2, 28)


def test_clean_payload_long_and_wide(tmp_path) -> None:
    long_rows, wide_rows, quality = source.clean_payload(_payload())

    assert len(long_rows) == 16  # 15 产品 7 月 + 钢坯 8 月（线材 8 月缺报跳过）
    assert long_rows[0]["period"] == date(2026, 7, 31)
    billets = [row for row in long_rows if row["product"] == "钢坯及方坯"]
    assert len(billets) == 2  # 7 月区间报价 + 8 月新价
    assert billets[0]["midpoint"] == 610.0
    assert billets[1]["period"] == date(2026, 8, 31)
    # 线材只有 7 月一行；宽表 8 月该格为空
    wire = [row for row in long_rows if row["product"] == "线材"]
    assert len(wire) == 1
    wide_latest = wide_rows[0]
    assert wide_latest["month_end"] == "2026-08-31"
    assert wide_latest["阿联酋:钢材进口报价:线材:CFR/CPT:区间中值"] is None
    assert wide_latest["阿联酋:钢材进口报价:钢坯及方坯:CFR/CPT:区间中值"] == 630.0
    assert quality["long_row_count"] == 16


def test_clean_payload_rejects_overlapping_origin_segments() -> None:
    payload = _payload()
    payload["data"].append(
        {
            "product": "Billets Blooms",
            "origin": "India",
            "prices": {"2026-07-01": "600"},
        }
    )
    with pytest.raises(ValueError, match="Overlapping MEsteel origin segments"):
        source.clean_payload(payload)


def test_clean_payload_rejects_unknown_product() -> None:
    payload = _payload()
    payload["data"][0]["product"] = "Super Alloy"
    with pytest.raises(ValueError, match="MEsteel product catalogue changed"):
        source.clean_payload(payload)


def test_update_roundtrip_loads_monthly_table(tmp_path, monkeypatch) -> None:
    raw_path = tmp_path / "mesteel_monthly_prices.json"
    raw_path.write_text(
        json.dumps(_payload(), ensure_ascii=False), encoding="utf-8-sig"
    )
    monkeypatch.setattr(source, "RAW_PATH", raw_path)
    monkeypatch.setattr(
        source, "QUALITY_PATH", tmp_path / "quality_report.json"
    )

    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = source.update(con, skip_download=True)

    assert outcome["status"] == "ok"
    assert outcome["rows"] == 16
    rows = con.execute(
        "SELECT period, product, midpoint FROM mesteel_monthly ORDER BY period"
    ).fetchall()
    assert len(rows) == 16
    assert rows[0][0] == date(2026, 7, 31)
    # 字典：15 个产品全部入库
    count = con.execute(
        "SELECT count(*) FROM meta_indicator_dictionary "
        "WHERE indicator_name LIKE '阿联酋:钢材进口报价:%'"
    ).fetchone()[0]
    assert count == len(source.PRODUCTS)
    con.close()


def test_merge_builds_wide_csv(tmp_path) -> None:
    con = db.connect(":memory:")
    db.init_schema(con)
    rows, _wide, _quality = source.clean_payload(_payload())
    db.replace(
        con,
        "mesteel_monthly",
        [
            {
                "period": r["period"],
                "product": r["product"],
                "lower": r["low"],
                "upper": r["high"],
                "midpoint": r["midpoint"],
                "origin_label": r["origin"],
            }
            for r in rows
        ],
    )
    csv_path = source._build_wide_csv(con)
    con.close()
    try:
        text = csv_path.read_text(encoding="utf-8-sig")
        assert text.splitlines()[0].startswith("month_end,")
        assert "阿联酋:钢材进口报价:线材:CFR/CPT:区间中值" in text.splitlines()[0]
        assert len(text.splitlines()) == 3  # header + 2026-07 + 2026-08
    finally:
        csv_path.unlink(missing_ok=True)
