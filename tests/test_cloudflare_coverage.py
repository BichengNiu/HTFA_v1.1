"""Weekly publication uses the proven API interval end, not its Monday timestamp."""

import json
from datetime import date

from htfa.monitoring.uae.jobs import db, source_cloudflare_radar as source


def test_weekly_cutoff_preserves_october_and_excludes_a_november_crossing(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "RAW_DIR", tmp_path)
    name = "weekly.json"
    payload = {"result": {
        "ae": {"timestamps": ["2026-10-19T00:00:00Z", "2026-10-26T00:00:00Z"],
               "values": [0.9, 1.0]},
        "meta": {"normalization": "MIN0_MAX", "dateRange": [{"endTime": "2026-11-02T00:00:00Z"}]},
    }}
    (tmp_path / name).write_text(json.dumps(payload))
    rows = [(date(2026, 10, 19), 90), (date(2026, 10, 26), 100)]
    with db.connect(":memory:") as con:
        con.execute(source._TABLE_DDL)
        inputs = [dict(period=p, indicator=source.INDICATOR_W, value=v, source_file=name)
                  for p, v in rows]
        source._ingest(con, inputs)
        source._store_coverage(con, inputs)
        cutoff = source._weekly_cutoff(con, rows, today=date(2026, 11, 3))
        assert cutoff == date(2026, 10, 31)
        from datetime import timedelta

        assert [p for p, _ in rows if p + timedelta(days=6) <= cutoff] == [date(2026, 10, 19)]
        # A source window ending mid-October cannot make October complete.
        con.execute("UPDATE cloudflare_radar_coverage SET observed_through='2026-10-29'")
        assert source._weekly_cutoff(con, rows, today=date(2026, 11, 3)) == date(2026, 9, 30)


def test_missing_coverage_keeps_conservative_old_boundary():
    rows = [(date(2026, 10, 26), 100)]
    with db.connect(":memory:") as con:
        con.execute(source._TABLE_DDL)
        assert source._weekly_cutoff(con, rows, today=date(2026, 11, 3)) == date(2026, 9, 30)
