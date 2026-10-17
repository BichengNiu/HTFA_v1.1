"""EIA all-liquids scope and calendar-day weighted complete quarters."""

from datetime import date

import pytest

from htfa.jobs.uae_data import db, source_eia_liquids as source


def record(period, value):
    return {"period": period, "value": str(value), "countryRegionId": "ARE",
            "productId": "53", "activityId": "1", "unit": "TBPD"}


def test_calendar_day_weighted_quarters_match_existing_series_and_omit_partial_quarter():
    monthly = source.parse_monthly({"response": {"total": 4, "data": [
        record("2024-01", 1000), record("2024-02", 2000),
        record("2024-03", 3000), record("2024-04", 4000),
    ]}})
    quarterly = source.quarterly_observations(monthly)
    assert quarterly == [(date(2024, 3, 31), pytest.approx((31 + 29 * 2 + 31 * 3) / 91))]


@pytest.mark.parametrize("change", ["scope", "duplicate", "missing_month", "truncated"])
def test_invalid_or_different_scope_data_is_rejected(change):
    rows = [record("2024-01", 1000), record("2024-02", 2000), record("2024-03", 3000)]
    if change == "scope":
        rows[0]["productId"] = "57"  # Crude oil is not all liquids.
    elif change == "duplicate":
        rows.append(rows[0])
    elif change == "missing_month":
        rows.pop(1)
    count = len(rows) + (1 if change == "truncated" else 0)
    with pytest.raises(ValueError):
        source.parse_monthly({"response": {"total": count, "data": rows}})


def test_update_stores_monthly_then_quarterly_and_refuses_regression(tmp_path, monkeypatch):
    import json
    path = tmp_path / "monthly.json"
    monkeypatch.setattr(source, "RAW_PATH", path)
    rows = [record(f"2024-{m:02}", 1000 + m) for m in range(1, 7)]
    path.write_text(json.dumps({"response": {"total": len(rows), "data": rows}}))
    con = db.connect(":memory:")
    db.init_schema(con)
    source.update(con, skip_download=True)
    assert con.execute("SELECT count(*) FROM eia_liquids_monthly").fetchone()[0] == 6
    before = con.execute("SELECT * FROM eia_liquids_quarterly ORDER BY 1").fetchall()
    path.write_text(json.dumps({"response": {"total": 3, "data": rows[:3]}}))
    with pytest.raises(ValueError, match="回退"):
        source.update(con, skip_download=True)
    assert con.execute("SELECT * FROM eia_liquids_quarterly ORDER BY 1").fetchall() == before
    con.close()
