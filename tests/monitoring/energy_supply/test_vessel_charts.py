"""Vessel charts count distinct ships in observed periods, with unknown gaps."""
from datetime import date
import unittest
from unittest.mock import patch
from htfa.monitoring.energy_supply import vessel_charts
class VesselChartsTest(unittest.TestCase):
    def test_stock_uses_fresh_latest_positions_and_period_end_sample_not_daily_sum(self):
        rows = [
            {"mmsi": "1", "observed_at": "2026-10-15T01:00:00Z", "region": "波斯湾"},
            {"mmsi": "2", "observed_at": "2026-10-15T08:00:00Z", "region": "波斯湾", "category": "cargo"},
            {"mmsi": "2", "observed_at": "2026-10-15T09:00:00Z", "region": "阿曼湾", "category": "cargo"},
            {"mmsi": "3", "observed_at": "2026-10-15T09:00:00Z", "region": "波斯湾", "category": "tanker"},
            {"mmsi": "4", "observed_at": "2026-10-16T09:00:00Z", "region": "波斯湾", "category": "tanker"},
        ]
        args = (rows, date(2026,10,15), date(2026,10,16))
        daily = vessel_charts.stock_series(*args, "日度", ["未知船籍"], ["未知目的地"])
        self.assertEqual(daily[0]['波斯湾'], 1)  # Stale ship 1 excluded; ship 2 moved.
        self.assertEqual(daily[0]['阿曼湾'], 1)
        self.assertEqual(daily[0]['sample_at'], '2026-10-15T09:00:00+00:00')
        weekly = vessel_charts.stock_series(*args, "周度", ["未知船籍"], ["未知目的地"])
        self.assertEqual(weekly[0]['波斯湾'], 1)
        self.assertEqual(weekly[0]['cargo'], 0)  # Last sample, not a union of days.

    def test_daily_axis_shows_calendar_dates_without_hour_or_offset_labels(self):
        from matplotlib.figure import Figure
        save = Figure.savefig
        checked = []
        def inspect(figure, *args, **kwargs):
            figure.canvas.draw()
            ax = figure.axes[0]
            labels = [t.get_text() for t in ax.get_xticklabels() if t.get_text()]
            self.assertEqual(labels, ['2026-10-15', '2026-10-16', '2026-10-17'])
            self.assertFalse(ax.xaxis.get_offset_text().get_visible())
            self.assertEqual(ax.get_xlabel(), '')
            checked.append(True)
            return save(figure, *args, **kwargs)
        rows = tuple((date(2026,10,d), date(2026,10,d), date(2026,10,d), *([1]*6))
                     for d in (15,16,17))
        with patch.object(Figure, 'savefig', autospec=True, side_effect=inspect):
            images = vessel_charts.chart_images.__wrapped__(rows, '日度')
        self.assertEqual(len(images), 6)
        self.assertEqual(len(checked), 6)

    def test_type_counts_deduplicate_across_waters_and_use_latest_classification(self):
        rows = [
            {"mmsi": "1", "observed_at": "2026-10-05T01:00:00Z", "region": "波斯湾", "category": "unknown"},
            {"mmsi": "1", "observed_at": "2026-10-06T01:00:00Z", "region": "阿曼湾", "category": "tanker"},
            {"mmsi": "2", "observed_at": "2026-10-06T01:00:00Z", "region": "波斯湾", "category": "cargo"},
            {"mmsi": "3", "observed_at": "2026-10-06T01:00:00Z", "region": "波斯湾", "category": "passenger"},
        ]
        records = vessel_charts.aggregate(rows, date(2026,10,5), date(2026,10,18), "周度",
                                          ["未知船籍"], ["未知目的地"])
        self.assertEqual([records[0][key] for key in vessel_charts.CHART_TYPES], [1,1,1])
        self.assertTrue(all(records[1][key] is None for key in vessel_charts.CHART_TYPES))
        self.assertEqual(list(vessel_charts.CHART_LABELS)[:3], ["霍尔木兹海峡", "阿曼湾", "波斯湾"])
        self.assertEqual(len(vessel_charts.CHART_LABELS), 6)

    def test_distinct_vessels_across_reports_days_and_sources(self):
        rows = [{"mmsi": ship, "observed_at": f"2026-10-{day:02}T12:00:00Z",
                 "region": "波斯湾", "flag_country": "中国", "destination": "DUBAI"}
                for day, ship in [(5, "1"), (5, "1"), (6, "1"), (6, "2"), (8, "3")]]
        args = (date(2026, 10, 5), date(2026, 10, 8))
        daily = vessel_charts.aggregate(rows, *args, "日度", ["中国"], ["迪拜"])
        self.assertEqual([r["波斯湾"] for r in daily], [1, 2, None, 1])
        weekly = vessel_charts.aggregate(rows, *args, "周度", ["中国"], ["迪拜"])
        self.assertEqual(weekly[0]["波斯湾"], 3)
        self.assertIsNone(weekly[0]["阿曼湾"])
        empty = vessel_charts.aggregate(rows, *args, "日度", [], [])
        self.assertEqual([r["波斯湾"] for r in empty], [0, 0, None, 0])

    def test_unknown_speed_is_not_counted_as_berthed_and_chinese_flag_is_explicit(self):
        rows = [{"sog": None, "category": "unknown", "mmsi": "413000000"},
                {"sog": 0, "category": "tanker", "flag": "CN"},
                {"sog": 4, "category": "cargo", "flag": "HK"},
                {"sog": 2, "category": "passenger", "flag": "PA"}]
        self.assertEqual([value for _, value in vessel_charts.metrics(rows, True)], [2, 1, 1, 1, 2, 1])
        self.assertTrue(all(value == "—" for _, value in vessel_charts.metrics([], False)))

    def test_filters_use_unknown_options_and_clip_dates(self):
        row = {"observed_at": "2026-10-01T23:59:00Z", "mmsi": "1", "region": "波斯湾"}
        self.assertTrue(vessel_charts.matches(row, ["未知船籍"], ["未知目的地"]))
        records = vessel_charts.aggregate([row], date(2026, 10, 2), date(2026, 10, 2),
                                          "月度", ["未知船籍"], ["未知目的地"])
        self.assertIsNone(records[0]["波斯湾"])
        self.assertEqual(records[0]["period_start"], date(2026, 10, 2))


if __name__ == "__main__":
    unittest.main()
