"""Tests for the classified UN Comtrade equipment pipeline."""

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "capitalImports"
    / "process_and_merge.py"
)
SPEC = importlib.util.spec_from_file_location("capital_imports_process", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PROCESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROCESS)


def test_exact_hs6_codes_map_to_final_categories() -> None:
    assert PROCESS.series_for_code("847950") == {"manufacturing_equipment"}
    assert PROCESS.series_for_code("842952") == {
        "civil_construction_equipment"
    }
    assert PROCESS.series_for_code("841182") == {"energy_project_equipment"}
    assert PROCESS.series_for_code("843041") == {"drilling_equipment"}
    assert PROCESS.series_for_code("860210") == {"port_rail_equipment"}
    assert PROCESS.series_for_code("842620") == {
        "civil_construction_equipment"
    }
    assert PROCESS.series_for_code("841340") == {
        "civil_construction_equipment"
    }
    assert PROCESS.series_for_code("847720") == {
        "manufacturing_equipment"
    }
    assert PROCESS.series_for_code("870540") == {
        "civil_construction_equipment"
    }
    assert PROCESS.series_for_code("840682") == {
        "energy_project_equipment"
    }
    assert PROCESS.series_for_code("870520") == {"drilling_equipment"}
    assert PROCESS.series_for_code("842612") == {"port_rail_equipment"}
    assert PROCESS.series_for_code("842611") == {"port_rail_equipment"}
    assert PROCESS.series_for_code("842699") == {
        "civil_construction_equipment"
    }
    assert PROCESS.series_for_code("845910") == {
        "manufacturing_equipment"
    }
    assert PROCESS.series_for_code("860400") == {"port_rail_equipment"}
    assert PROCESS.series_for_code("847790") == set()
    assert PROCESS.series_for_code("847420") == set()


def test_month_grid_stops_at_latest_observed_month() -> None:
    months = PROCESS.month_grid("202606")

    assert months[0] == "202606"
    assert months[-1] == "201701"
    assert "202607" not in months
    assert len(months) == 114


def test_item_quantity_prefers_reported_alternate_count() -> None:
    row = {
        "qtyUnitCode": 5,
        "qty": 6.001,
        "isQtyEstimated": True,
        "altQtyUnitCode": 5,
        "altQty": 7,
        "isAltQtyEstimated": False,
    }

    assert PROCESS.item_quantity(row) == (7.0, False, "altQty")


def test_aggregate_uses_direct_value_then_category_mirror_fallback(
    monkeypatch,
) -> None:
    direct = [
        {
            "period": "201701",
            "cmdCode": "847950",
            "primaryValue": 100,
            "qtyUnitCode": 5,
            "qty": 10,
            "isQtyEstimated": True,
        }
    ]
    mirror = [
        {
            "period": "201701",
            "reporterCode": 1,
            "cmdCode": "847950",
            "primaryValue": 900,
            "qtyUnitCode": 5,
            "qty": 99,
            "isQtyEstimated": False,
        },
        {
            "period": "201701",
            "reporterCode": 1,
            "cmdCode": "842952",
            "primaryValue": 200,
            "qtyUnitCode": 5,
            "qty": 20,
            "isQtyEstimated": False,
        },
        {
            "period": "201702",
            "reporterCode": 1,
            "cmdCode": "847950",
            "primaryValue": 300,
            "qtyUnitCode": 5,
            "qty": 30,
            "isQtyEstimated": False,
        },
        {
            "period": "201702",
            "reporterCode": 2,
            "cmdCode": "847950",
            "primaryValue": 400,
        },
    ]
    monkeypatch.setattr(
        PROCESS,
        "load_reporters",
        lambda: {
            1: {"reporterDesc": "Country A", "isGroup": False},
            2: {"reporterDesc": "Region Group", "isGroup": True},
        },
    )
    monkeypatch.setattr(
        PROCESS,
        "iter_raw_rows",
        lambda source: iter(
            direct if source == "equipment_uae_reported" else mirror
        ),
    )

    rows, detail, sources, quantity_detail = PROCESS.aggregate()
    by_month = {row["month"]: row for row in rows}

    assert by_month["201701"]["manufacturing_equipment_usd"] == 100
    assert by_month["201701"]["civil_construction_equipment_usd"] == 200
    assert by_month["201702"]["manufacturing_equipment_usd"] == 300
    assert by_month["201701"]["manufacturing_equipment_units"] == 10
    assert by_month["201701"]["civil_construction_equipment_units"] == 20
    assert by_month["201702"]["manufacturing_equipment_units"] == 30
    assert sources[("201701", "manufacturing_equipment")] == "uae_reported"
    assert sources[("201701", "civil_construction_equipment")] == (
        "all_partner_mirror"
    )
    assert sources[("201702", "energy_project_equipment")] == "missing"
    assert {row["reporter_code"] for row in detail} == {1}
    manufacturing_quantity = [
        row
        for row in quantity_detail
        if row["month"] == "201701"
        and row["series"] == "manufacturing_equipment"
    ]
    assert manufacturing_quantity == [
        {
            "month": "201701",
            "series": "manufacturing_equipment",
            "hs6": "847950",
            "source": "uae_reported",
            "units": 10.0,
            "reported_units": 0.0,
            "estimated_units": 10.0,
            "reporter_count": 1,
        }
    ]
