"""A backup must recover a missed run without duplicating a successful one."""
from datetime import datetime, timezone
import unittest

from htfa.monitoring.energy_supply.jobs.snapshot_retry import decision


def full_snapshot(when):
    return {"completed_at": when,
            "source_results": {source: {"last_successful_collection": when} for source in ("ais", "ports", "chokepoints")}}


class SnapshotRetryTest(unittest.TestCase):
    now = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)  # 13:00 Dubai

    def test_no_run_or_yesterday_failure_requires_retry(self):
        for marker in [None, {}, full_snapshot("2026-10-26T04:01:00+00:00")]:
            self.assertEqual(decision(marker, self.now)["status"], "retry_due")

    def test_successful_primary_or_manual_recovery_skips_duplicate(self):
        for when in ["2026-10-27T04:01:00+00:00", "2026-10-27T05:41:01+00:00"]:
            result = decision(full_snapshot(when), self.now)
            self.assertEqual(result["status"], "skipped_already_published")
            self.assertEqual(result["primary_window_start"], "2026-10-27T08:00:00+04:00")

    def test_catalog_change_or_notification_is_not_full_collection(self):
        for marker in [{"completed_at": "2026-10-27T05:00:00+00:00", "mode": "catalog_review"},
                       {"completed_at": "2026-10-27T05:00:00+00:00", "after": {"counts": {}}}]:
            self.assertEqual(decision(marker, self.now)["status"], "retry_due")

    def test_midnight_is_not_a_new_primary_window(self):
        # 01:00 Oct28 Dubai still belongs to Oct27's 08:00 primary window.
        now = datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc)
        self.assertEqual(decision(full_snapshot("2026-10-27T04:01:00+00:00"), now)["status"],
                         "skipped_already_published")

    def test_pre_primary_success_does_not_replace_today_primary(self):
        self.assertEqual(decision(full_snapshot("2026-10-27T03:00:00+00:00"), self.now)["status"],
                         "retry_due")

    def test_future_or_timezone_free_success_cannot_silently_skip(self):
        for when in ["2026-10-28T04:01:00+00:00", "2026-10-27T04:01:00"]:
            with self.assertRaises(ValueError):
                decision(full_snapshot(when), self.now)

    def test_partial_publication_cannot_hide_failed_source_behind_new_publication_time(self):
        snapshot = {**full_snapshot('2026-10-27T08:00:00+00:00'), 'full_collection_complete': False,
                    'source_results': {
                        'ais': {'status': 'ok', 'last_successful_collection': '2026-10-27T08:00:00+00:00'},
                        **{source: {'status': 'error', 'last_successful_collection': '2026-10-26T04:01:00+00:00'}
                           for source in ('ports', 'chokepoints')}}}
        result = decision(snapshot, self.now)
        self.assertEqual(result['status'], 'retry_due')
        self.assertEqual(result['pending_sources'], ['ports', 'chokepoints'])
        for source in ('ports', 'chokepoints'):
            snapshot['source_results'][source]['last_successful_collection'] = '2026-10-27T08:30:00+00:00'
        self.assertEqual(decision(snapshot, self.now)['status'], 'skipped_already_published')

    def test_portwatch_success_does_not_mark_old_ais_as_success(self):
        result = decision({'completed_at': '2026-10-27T08:30:00+00:00',
                           'source_results': {source: {'last_successful_collection': '2026-10-27T08:30:00+00:00'}
                                              for source in ('ports', 'chokepoints')}}, self.now)
        self.assertEqual(result['pending_sources'], ['ais'])
