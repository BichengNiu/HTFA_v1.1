from pathlib import Path
"""Keep one stable current report per vessel across multiple AIS sources."""
from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from htfa.monitoring.energy_supply import ais_history
from htfa.monitoring.energy_supply import data_store
class AISSnapshotDedupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(data_store.job_database(Path(self.temp.name) / "test.duckdb"))

    def test_same_observation_from_two_sources_returns_one_latest_received_row(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=3)
        earlier = observed + timedelta(seconds=1)
        later = observed + timedelta(seconds=2)
        with data_store.connect() as conn:
            for source, received, lon in (
                ("AISStream", earlier, 56.0),
                ("Open Waters", later, 56.1),
            ):
                payload = {
                    "mmsi": "123456789", "observed_at": observed.isoformat(),
                    "received_at": received.isoformat(), "source": source,
                    "data_source": source, "lat": 25.0, "lon": lon,
                }
                conn.execute(
                    "INSERT INTO ais_reports VALUES (?,?,?,?)",
                    ("123456789", observed.isoformat(), source,
                     json.dumps(payload, ensure_ascii=False)),
                )

        rows = ais_history.latest_snapshot()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "Open Waters")
        self.assertEqual(rows[0]["lon"], 56.1)

    def test_fallback_keeps_only_the_last_available_time_window(self):
        self.assertEqual(ais_history.latest_snapshot(fallback_to_latest=True), [])
        now = datetime.now(timezone.utc)
        positions = (("123456789", now - timedelta(days=1)),
                     ("223456789", now - timedelta(days=1, minutes=30)),
                     ("323456789", now - timedelta(days=10)))
        with data_store.connect() as conn:
            for mmsi, observed in positions:
                conn.execute("INSERT INTO ais_reports VALUES (?,?,?,?)", (
                    mmsi, observed.isoformat(), "test", json.dumps({
                        "mmsi": mmsi, "observed_at": observed.isoformat(),
                        "lat": 26.0, "lon": 53.0,
                    }),
                ))

        self.assertEqual(ais_history.latest_snapshot(), [])
        rows = ais_history.latest_snapshot(fallback_to_latest=True)
        self.assertEqual({row["mmsi"] for row in rows}, {"123456789", "223456789"})
        self.assertEqual(rows[0]["observed_at"], positions[0][1].isoformat())

    def test_fallback_does_not_mix_old_positions_into_a_recent_snapshot(self):
        now = datetime.now(timezone.utc)
        with data_store.connect() as conn:
            for mmsi, observed in (("123456789", now - timedelta(minutes=1)),
                                   ("223456789", now - timedelta(days=1))):
                conn.execute("INSERT INTO ais_reports VALUES (?,?,?,?)", (
                    mmsi, observed.isoformat(), "test", json.dumps({"mmsi": mmsi}),
                ))

        rows = ais_history.latest_snapshot(fallback_to_latest=True)
        self.assertEqual([row["mmsi"] for row in rows], ["123456789"])


if __name__ == "__main__":
    unittest.main()
