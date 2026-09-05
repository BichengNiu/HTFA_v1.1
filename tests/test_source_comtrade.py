"""Tests for ``data/source_comtrade.py``（DuckDB 入库版）。"""

import json
import sys
from datetime import date
from pathlib import Path

from htfa.jobs.uae_data import db  # noqa: E402
from htfa.jobs.uae_data import source_comtrade as source  # noqa: E402


def _write_reporters(tmp_path: Path) -> Path:
    path = tmp_path / "reporters.json"
    path.write_text(
        json.dumps(
            {
                "results": [
                    {"reporterCode": 784, "reporterDesc": "United Arab Emirates"},
                    {"reporterCode": 156, "reporterDesc": "China"},
                    {"reporterCode": 699, "reporterDesc": "India"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_month(tmp_path: Path, source_name: str, period: str, rows: list) -> None:
    directory = tmp_path / source_name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source_name}_{period}.json"
    path.write_text(json.dumps({"data": rows}), encoding="utf-8")


def _uae_row(period: str, code: str, value: float, units: float) -> dict:
    return {
        "period": period,
        "cmdCode": code,
        "primaryValue": value,
        "qty": units,
        "qtyUnitCode": 5,
        "isQtyEstimated": False,
        "altQty": None,
        "altQtyUnitCode": None,
        "isAltQtyEstimated": False,
    }


def test_item_quantity_prefers_non_estimated_alt_qty() -> None:
    row = {
        "qty": 10,
        "qtyUnitCode": 5,
        "isQtyEstimated": True,
        "altQty": 12,
        "altQtyUnitCode": 5,
        "isAltQtyEstimated": False,
    }
    value, estimated, field = source.item_quantity(row)
    assert (value, estimated, field) == (12.0, False, "altQty")


def test_month_grid_newest_first() -> None:
    grid = source.month_grid("202603")
    assert grid[:3] == ["202603", "202602", "202601"]
    assert grid[-1] == "201701"
    assert len(grid) == 12 * (2026 - 2017) + 3


def test_aggregate_prefers_uae_direct_and_mirror_fallback(tmp_path, monkeypatch) -> None:
    reporters = _write_reporters(tmp_path)
    monkeypatch.setattr(source, "REPORTERS_PATH", reporters)
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)

    # 2026-03：UAE 直报存在（845710 属于制造业设备）
    _write_month(
        tmp_path,
        "equipment_uae_reported",
        "202603",
        [_uae_row("202603", "845710", 1_000_000.0, 10.0)],
    )
    # 2026-02：UAE 无直报，镜像有中国出口（842911 属于土建施工设备）
    _write_month(
        tmp_path,
        "equipment_uae_reported",
        "202602",
        [],
    )
    _write_month(
        tmp_path,
        "equipment_all_mirror",
        "202602",
        [
            {
                "period": "202602",
                "cmdCode": "842911",
                "reporterCode": 156,
                "primaryValue": 500_000.0,
                "qty": 5.0,
                "qtyUnitCode": 5,
                "isQtyEstimated": False,
                "altQty": None,
                "altQtyUnitCode": None,
                "isAltQtyEstimated": False,
            }
        ],
    )

    rows, detail, sources, quantity_detail = source.aggregate()

    # 旧口径：month_grid 从最新观测月一直铺到 2017-01，缺失月值为 None
    assert rows[0]["month"] == "202603"
    assert rows[-1]["month"] == "201701"
    assert len(rows) == 12 * (2026 - 2017) + 3
    march = rows[0]
    assert march["manufacturing_equipment_usd"] == 1_000_000.0
    assert march["manufacturing_equipment_usd_mn"] == 1.0
    assert march["manufacturing_equipment_units"] == 10.0
    assert march["civil_construction_equipment_usd"] is None
    february = rows[1]
    assert february["civil_construction_equipment_usd"] == 500_000.0
    assert february["manufacturing_equipment_usd"] is None
    assert sources[("202603", "manufacturing_equipment")] == "uae_reported"
    assert sources[("202602", "civil_construction_equipment")] == "all_partner_mirror"
    assert len(detail) == 1
    assert detail[0]["reporter_name"] == "China"
    assert len(quantity_detail) == 2


def test_to_db_rows_and_roundtrip(tmp_path, monkeypatch) -> None:
    reporters = _write_reporters(tmp_path)
    monkeypatch.setattr(source, "REPORTERS_PATH", reporters)
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    _write_month(
        tmp_path,
        "equipment_uae_reported",
        "202603",
        [_uae_row("202603", "845710", 1_000_000.0, 10.0)],
    )
    rows, detail, sources, quantity_detail = source.aggregate()
    monthly, detail_rows, quantity_rows = source._to_db_rows(
        rows, detail, quantity_detail
    )

    con = db.connect(":memory:")
    db.init_schema(con)
    db.replace(con, "comtrade_monthly", monthly)
    db.replace(con, "comtrade_partner_detail", detail_rows)
    db.replace(con, "comtrade_quantity_detail", quantity_rows)

    stored = con.execute(
        "SELECT period, category, value, units FROM comtrade_monthly"
    ).fetchall()
    assert stored == [(date(2026, 3, 31), "manufacturing_equipment", 1_000_000.0, 10.0)]

    rebuilt = source._reconstruct_rows(con)
    con.close()
    assert rebuilt[0]["month"] == "202603"
    assert rebuilt[0]["manufacturing_equipment_usd_mn"] == 1.0
    assert rebuilt[0]["civil_construction_equipment_usd"] is None


def test_dictionary_rows_cover_amounts_and_units() -> None:
    rows = source._dictionary_rows()
    names = [row["indicator_name"] for row in rows]
    assert "阿联酋:进口:制造业设备:当月值" in names
    assert "阿联酋:进口:钻探设备:台数:当月值" in names
    assert len(rows) == len(source.SERIES) * 2
