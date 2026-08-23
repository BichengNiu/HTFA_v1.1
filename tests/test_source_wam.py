"""Tests for the WAM military-strike registry and DuckDB pipeline."""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "UAE" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402
import source_wam as source  # noqa: E402


def test_daily_registry_and_monthly_pressure() -> None:
    daily = source.load_daily_observations()
    monthly = source.build_monthly_observations(daily)

    assert len(daily) == 176
    assert daily[0]["date"].isoformat() == "2026-02-28"
    assert daily[-1]["date"].isoformat() == "2026-08-22"
    may = next(row for row in monthly if row.period.isoformat() == "2026-05-31")
    assert (may.ballistic_missiles, may.cruise_missiles, may.uavs) == (14, 4, 17)
    assert may.unclassified_missiles == 0
    assert may.attack_days == 5
    assert may.asset_attack_days == 1
    assert may.strike_intensity_log == pytest.approx(45.00377407)
    assert 0.0 <= may.strike_intensity_index <= 100.0
    assert min(row.strike_intensity_index for row in monthly) == pytest.approx(0.0)
    assert max(row.strike_intensity_index for row in monthly) == pytest.approx(100.0)


def test_update_roundtrip_creates_daily_monthly_and_dictionary_tables() -> None:
    con = db.connect(":memory:")
    db.init_schema(con)
    outcome = source.update(con, skip_download=True)

    assert outcome["status"] == "ok"
    assert con.execute(
        "SELECT COUNT(*) FROM detail.wam_military_strike_daily"
    ).fetchone()[0] == 176
    assert con.execute(
        "SELECT COUNT(*) FROM wam_military_strike_monthly"
    ).fetchone()[0] == 7
    assert con.execute(
        "SELECT MIN(strike_intensity_index), MAX(strike_intensity_index) "
        "FROM wam_military_strike_monthly"
    ).fetchone() == pytest.approx((0.0, 100.0))
    assert con.execute(
        "SELECT COUNT(*) FROM main.wam_military_strike_daily"
    ).fetchone()[0] == 176
    assert con.execute(
        "SELECT COUNT(*) FROM meta_indicator_dictionary WHERE source = ?",
        [source.SOURCE_NAME],
    ).fetchone()[0] == len(source.INDICATORS)
    con.close()


def test_registry_rejects_inconsistent_pressure(tmp_path: Path) -> None:
    source_path = tmp_path / "daily.csv"
    shutil.copy2(source.DAILY_PATH, source_path)
    rows = []
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    rows[0]["strike_intensity_log"] = "0"
    with source_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="strike_intensity_log"):
        source.load_daily_observations(source_path)


def test_registry_keeps_unclassified_attack_out_of_pressure() -> None:
    row = next(row for row in source.load_daily_observations() if row["date"].isoformat() == "2026-08-08")
    assert row["unclassified_missiles"] == 1
    assert row["attack_any"] is True
    assert row["strike_intensity_log"] == 0
