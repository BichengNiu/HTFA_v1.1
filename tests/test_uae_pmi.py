"""Tests for public UAE headline PMI download and processing helpers."""

import base64
import gzip
import json
from datetime import date

from scripts.data_sources.uae_pmi.download_uae_pmi import (
    decode_chart_response,
    parse_chart_config,
)
from scripts.data_sources.uae_pmi.process_uae_pmi import (
    PmiObservation,
    build_quality_report,
    load_observations,
)


def test_parse_chart_config_reads_public_runtime_values() -> None:
    page = """
    <script>
    TEChartsDatasource = 'https://example.test';
    TEChartsToken='public-token';
    TEObfuscationkey='public-key';
    TESymbol='UNITEDARAMANPMI';
    TELastUpdate='20260731000000';
    </script>
    """

    config = parse_chart_config(page)

    assert config["TEChartsDatasource"] == "https://example.test"
    assert config["TESymbol"] == "UNITEDARAMANPMI"
    assert config["TELastUpdate"] == "20260731000000"


def test_decode_chart_response_reverses_public_web_algorithm() -> None:
    payload = [
        {"series": [{"serie": {"data": [[52.7, 0, None, "2026-07-01"]]}}]}
    ]
    key = b"public-key"
    compressed = bytearray(gzip.compress(json.dumps(payload).encode("utf-8")))
    for index in range(len(compressed)):
        compressed[index] ^= key[index % len(key)]
    envelope = json.dumps(base64.b64encode(compressed).decode("ascii")).encode("ascii")

    assert decode_chart_response(envelope, key.decode("ascii")) == payload


def test_load_observations_and_quality_report_accept_continuous_history() -> None:
    data = []
    year, month = 2024, 7
    for offset in range(25):
        current_month = month + offset
        current_year = year + (current_month - 1) // 12
        normalized_month = (current_month - 1) % 12 + 1
        reference_date = f"{current_year:04d}-{normalized_month:02d}-01"
        data.append([52.0 + offset / 10, 0, None, reference_date])
    payload = [
        {
            "series": [
                {
                    "serie": {
                        "country": "United Arab Emirates",
                        "frequency": "monthly",
                        "source": "S&P Global",
                        "data": data,
                    }
                }
            ]
        }
    ]
    class JsonPath:
        def read_text(self, *, encoding: str) -> str:
            assert encoding == "utf-8"
            return json.dumps(payload)

    observations = load_observations(JsonPath())
    report = build_quality_report(
        observations,
        {
            "observation_count": 25,
            "source_last_update": "20260731000000",
            "coverage_note": "limited sample",
        },
        today=date(2026, 8, 13),
    )

    assert observations[0] == PmiObservation(period="2024-07", value=52.0)
    assert observations[-1].period == "2026-07"
    assert report["status"] == "passed"
    assert report["coverage"]["missing_periods"] == []
