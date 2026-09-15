"""Tests for the WAM military-strike registry and DuckDB pipeline."""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import pytest

from htfa.jobs.uae_data import db  # noqa: E402
from htfa.jobs.uae_data import source_wam as source  # noqa: E402


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
    expected_daily = len(source.load_effective_daily_observations())

    assert outcome["status"] == "ok"
    assert con.execute(
        "SELECT COUNT(*) FROM detail.wam_military_strike_daily"
    ).fetchone()[0] == expected_daily
    assert con.execute(
        "SELECT COUNT(*) FROM wam_military_strike_monthly"
    ).fetchone()[0] == 7
    assert con.execute(
        "SELECT MIN(strike_intensity_index), MAX(strike_intensity_index) "
        "FROM wam_military_strike_monthly"
    ).fetchone() == pytest.approx((0.0, 100.0))
    assert con.execute(
        "SELECT COUNT(*) FROM main.wam_military_strike_daily"
    ).fetchone()[0] == expected_daily
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


def test_auto_article_extraction_handles_direct_counts_and_singular_uav() -> None:
    direct = source.extract_auto_article_observation(
        {
            "url": "https://www.wam.ae/en/article/test-direct",
            "headline": "UAE air defences intercept 2 ballistic missiles, 3 UAVs",
            "article_body": (
                "ABU DHABI, 8th August, 2026 (WAM) -- The Ministry of Defence "
                "announced that UAE air defences intercepted two ballistic missiles "
                "and detected three UAVs today."
            ),
        }
    )
    singular = source.extract_auto_article_observation(
        {
            "url": "https://www.wam.ae/en/article/test-uav",
            "headline": "UAE Air Force responds to UAV over territorial waters",
            "article_body": (
                "ABU DHABI, 31st August, 2026 (WAM) -- The Ministry of Defence "
                "announced that the UAE Air Force responded to a UAV detected over "
                "the country's territorial waters."
            ),
        }
    )
    cumulative = source.extract_auto_article_observation(
        {
            "url": "https://www.wam.ae/en/article/test-cumulative",
            "headline": "UAE air defences intercept 165 ballistic missiles since onset",
            "article_body": (
                "ABU DHABI, 1st March, 2026 (WAM) -- The UAE air force dealt "
                "with 165 ballistic missiles since the start of the Iranian attack."
            ),
        }
    )

    assert direct is not None
    assert (direct["date"].isoformat(), direct["ballistic_missiles"], direct["uavs"]) == (
        "2026-08-08",
        2,
        3,
    )
    assert singular is not None
    assert singular["date"].isoformat() == "2026-08-31"
    assert singular["uavs"] == 1
    assert cumulative is None


def test_auto_daily_extension_fills_days_until_latest_event() -> None:
    base = source.load_daily_observations()
    rows = source.derive_auto_daily_observations(
        base,
        [
            {
                "url": "https://www.wam.ae/en/article/test-uav",
                "headline": "UAE Air Force responds to UAV over territorial waters",
                "article_body": (
                    "ABU DHABI, 31st August, 2026 (WAM) -- The Ministry of Defence "
                    "announced that the UAE Air Force responded to a UAV detected over "
                    "the country's territorial waters."
                ),
                "date_published": "2026-08-31T10:35:47+04:00",
            }
        ],
    )

    assert len(rows) == 9
    assert rows[0]["date"].isoformat() == "2026-08-23"
    assert rows[-1]["date"].isoformat() == "2026-08-31"
    assert all(not row["attack_any"] for row in rows[:-1])
    assert rows[-1]["uavs"] == 1
