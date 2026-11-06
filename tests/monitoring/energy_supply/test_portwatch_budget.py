"""Bound PortWatch request time across a single explicit refresh operation."""
import io
import json
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from datetime import date
from unittest.mock import patch
from pathlib import Path
import tempfile

import htfa.monitoring.energy_supply.processing.portwatch as portwatch
from htfa.monitoring.energy_supply.data import portwatch_client as transport
import htfa.monitoring.energy_supply.data.storage as data_store
class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class PortWatchBudgetTest(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(data_store.job_database(Path(temporary) / "test.duckdb"))

    def test_failed_date_statistics_falls_back_to_ordered_source_rows(self):
        with patch('htfa.monitoring.energy_supply.processing.portwatch.query', side_effect=[portwatch.PortWatchQueryError('Invalid URL'),
                {'features': [{'attributes': {'date': '2026-10-30'}}]}]) as query:
            self.assertEqual(portwatch._latest_day('https://example.test/query', 'empty'), date(2026, 10, 30))
        self.assertEqual(query.call_args.kwargs['orderByFields'], 'date DESC')
        self.assertEqual(query.call_args.kwargs['resultRecordCount'], 1)
        self.assertEqual(query.call_args.kwargs['outFields'], 'date')

    def test_request_timeout_is_capped_by_remaining_operation_budget(self):
        timeouts = []

        def response(_request, timeout):
            timeouts.append(timeout)
            return _Response(json.dumps({"features": []}).encode())

        with patch.object(transport, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("htfa.monitoring.energy_supply.data.portwatch_client.urlopen", side_effect=response):
            with transport.request_budget(0.25):
                result = portwatch.query("https://example.test/FeatureServer/0/query")

        self.assertEqual(result, {"features": []})
        self.assertEqual(len(timeouts), 1)
        self.assertGreater(timeouts[0], 0)
        self.assertLessEqual(timeouts[0], 0.25)

    def test_retry_backoff_stops_when_it_would_exceed_operation_budget(self):
        calls = []

        def response(_request, timeout):
            calls.append(timeout)
            return _Response(json.dumps({"error": {"message": "Too many requests"}}).encode())

        with patch.object(transport, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("htfa.monitoring.energy_supply.data.portwatch_client.urlopen", side_effect=response):
            with transport.request_budget(0.25):
                with self.assertRaises(transport.RequestBudgetExceeded):
                    portwatch.query("https://example.test/FeatureServer/0/query")

        self.assertEqual(len(calls), 1)

    def test_source_query_failure_preserves_details_and_safe_query_context(self):
        error = {"error": {"code": 400, "message": "", "details": ["Invalid query parameters"]}}
        with patch.object(transport, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("htfa.monitoring.energy_supply.data.portwatch_client.urlopen", side_effect=lambda *a, **k: _Response(json.dumps(error).encode())):
            with self.assertRaises(ValueError) as failure:
                portwatch.query("https://example.test/query", where="portid='port105'",
                                token="must-not-be-logged")
        message = str(failure.exception)
        self.assertIn("Invalid query parameters", message)
        self.assertIn("port105", message)
        self.assertNotIn("must-not-be-logged", message)

    def test_generic_arcgis_query_error_retries_without_changing_the_query(self):
        responses = [
            {"error": {"code": 400, "message": "Cannot perform query. Invalid query parameters."}},
            {"count": 14},
        ]
        requests = []
        def respond(request, timeout):
            requests.append(request.full_url)
            return _Response(json.dumps(responses.pop(0)).encode())
        with patch.object(transport, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("htfa.monitoring.energy_supply.data.portwatch_client.urlopen", side_effect=respond), patch("htfa.monitoring.energy_supply.data.portwatch_client._budget_sleep"):
            self.assertEqual(portwatch.query("https://example.test/query", where="portid='fso151'"),
                             {"count": 14})
        first = parse_qs(urlsplit(requests[0]).query)
        second = parse_qs(urlsplit(requests[1]).query)
        self.assertEqual(first['where'], second['where'])
        self.assertEqual(second['sqlFormat'], ['standard'])

    def test_persistent_backend_error_never_becomes_a_successful_empty_response(self):
        error = {"error": {"code": 400, "message": "Cannot perform query. Invalid query parameters."}}
        with patch.object(transport, "_LAST_REQUEST", time.monotonic() - 1), \
             patch("htfa.monitoring.energy_supply.data.portwatch_client.urlopen", side_effect=lambda *a, **k: _Response(json.dumps(error).encode())) as query, \
             patch("htfa.monitoring.energy_supply.data.portwatch_client._budget_sleep"):
            with self.assertRaisesRegex(ValueError, "Invalid query parameters"):
                portwatch.query("https://example.test/query")
        self.assertEqual(query.call_count, transport.QUERY_ATTEMPTS)

    def test_invalid_url_uses_alternate_formats_and_post_with_unchanged_data_query(self):
        calls = []
        def respond(request, timeout):
            params = parse_qs(request.data.decode() if request.data else urlsplit(request.full_url).query)
            calls.append((request.get_method(), params))
            data = ({'count': 434} if request.get_method() == 'POST' else
                    {'error': {'code': 400, 'message': 'Invalid URL', 'details': ['Invalid URL']}})
            return _Response(json.dumps(data).encode())
        with patch.object(transport, '_LAST_REQUEST', time.monotonic() - 1), \
             patch('htfa.monitoring.energy_supply.data.portwatch_client.urlopen', side_effect=respond), patch('htfa.monitoring.energy_supply.data.portwatch_client._budget_sleep'):
            result = portwatch.query('https://example.test/query', where="portid IN ('port27')", returnCountOnly='true')
        self.assertEqual(result, {'count': 434})
        self.assertEqual([method for method, _ in calls], ['GET', 'GET', 'GET', 'POST'])
        for _, params in calls:
            self.assertEqual(params['where'], ["portid IN ('port27')"])
            self.assertEqual(params['returnCountOnly'], ['true'])


if __name__ == "__main__":
    unittest.main()
