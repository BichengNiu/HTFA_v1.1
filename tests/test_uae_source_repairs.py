"""Checks for official source discovery and transport repairs."""

from datetime import date
from types import SimpleNamespace

import duckdb
import pytest

from htfa.jobs.uae_data import fetch_official_news as news
from htfa.jobs.uae_data import source_dld, source_rta, source_tdra
from htfa.jobs.uae_data import source_employment, source_eurostat_air


def test_tdra_discovers_by_official_title_with_absolute_media_url():
    page = '<div class="aegov-card x"><h6>Pre-paid Subscriptions</h6>'
    page += '<button data-item="changed-slug"></button>'
    page += '<a href="/-/media/Open-Data/test.ashx?a=1&amp;b=2">Download</a>'
    response = SimpleNamespace(text=page, raise_for_status=lambda: None)
    session = SimpleNamespace(get=lambda *a, **k: response)
    assert source_tdra._discover_downloads(session) == {
        "pre-paid-subscriptions": "https://tdra.gov.ae/-/media/Open-Data/test.ashx?a=1&b=2"
    }


def test_dld_continues_past_page_without_moasher(monkeypatch, tmp_path):
    pages = []
    def fetch(request, **kwargs):
        page = int(request.full_url.rsplit("=", 1)[1])
        pages.append(page)
        state = '{"props":{"pageProps":{"list":{"pagination":'
        state += f'{{"page":{page},"pageCount":2}}'
        state += '}}}}'
        body = f'<script id="__NEXT_DATA__">{state}</script>'
        if page == 2:
            body += '<a href="/en/insightshub/moasher/2024-monthly-november-240">Report</a>'
        return body
    monkeypatch.setattr(source_dld, "_http_read", fetch)
    monkeypatch.setattr(source_dld, "MOASHER_URLS_FILE", tmp_path / "urls.txt")
    assert source_dld._discover_moasher_urls() == [
        source_dld.MOASHER_BASE + "2024-monthly-november-240"
    ]
    assert pages == [1, 2]


def test_rta_mixed_line_endings_preserve_all_rows(tmp_path):
    path = tmp_path / "mixed.csv"
    original = (
        b'average_speed,date,route_direction,route_name,service_type,time_period,load_timestamp\r\n'
        b'"10","2026-07-31","N","1","Bus","AM","2026-08-01"\r\n'
        b'"20","2026-07-31","S","1","Bus","PM","2026-08-01"\n'
    )
    path.write_bytes(original)
    with duckdb.connect() as con:
        assert source_rta._aggregate_bus_speed(con, [path]) == {date(2026, 7, 31): 15}
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".rta-normalized-*"))


def test_rta_marine_reads_official_json_without_csv_fallback(tmp_path):
    path = tmp_path / "marine.json"
    path.write_text(
        '{"txn_date":"2026-08-07","location":"Dock \\"7\\""}\n'
        '{"txn_date":"2026-08-07","location":"Dock"}\n'
        ']Al Jadaf", "txn_date":"2026-08-07","txn_time":"22:28:00"},\n'
        ',[\n,,\n]\n', encoding="utf-8"
    )
    with duckdb.connect() as con:
        assert source_rta._aggregate_marine_daily([path]) == {date(2026, 8, 7): 3}
        path.write_text('{"txn_date":"not-a-date"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="invalid dates"):
            source_rta._aggregate_marine_daily([path])


def test_rta_incomplete_download_preserves_previous_file(monkeypatch, tmp_path):
    path = tmp_path / "export.json"
    path.write_bytes(b"previous")
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, *args): return iter([b"short"])
    monkeypatch.setattr(source_rta.requests, "get", lambda *a, **k: Response())
    with pytest.raises(OSError, match="Incomplete RTA export"):
        source_rta._download_to("url", path, retries=1, expected_size=100)
    assert path.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".rta-download-*"))


def test_rta_monthly_taxi_report_dates_are_normalized_before_grouping(tmp_path):
    path = tmp_path / "taxi.csv"
    path.write_text(
        'carrier,fleet_size,report_date,trips,load_timestamp\n'
        'A,10,2026-03-30,100,2026-04-01\n'
        'B,4,2026-03-31,50,2026-04-01\n', encoding="utf-8"
    )
    assert source_rta._aggregate_taxi_monthly([path]) == (
        {date(2026, 3, 31): 150}, {date(2026, 3, 31): 14}
    )


def _news_scan(monkeypatch, *, headline, body):
    item = {"Date": "Tuesday, October 13, 2026", "NewsTitle": headline,
            "FullText": body, "DetailPageLink": "/en/news/test"}
    payload = {"PageCount": 1, "TotalRecordCount": 1, "PageNo": 1, "Items": [item]}
    monkeypatch.setattr(news, "_fetch_listing_inputs", lambda: {})
    monkeypatch.setattr(news, "_fetch_news_page", lambda *a: payload)
    return news.discover_official_news(start=date(2020, 1, 1))


def test_ded_empty_title_keeps_valid_licence_body(monkeypatch):
    result = _news_scan(monkeypatch, headline="", body="Issued 123 new business licences in January 2026")
    assert result["observations"][0]["value"] == 123


def test_ded_unrelated_empty_article_is_reported(monkeypatch):
    result = _news_scan(monkeypatch, headline="Real estate completes projects", body="")
    assert result["articles_without_text"] == ["https://mediaoffice.ae/en/news/test"]


def test_ded_empty_licence_article_still_fails(monkeypatch):
    with pytest.raises(ValueError, match="licence news"):
        _news_scan(monkeypatch, headline="New business licences", body="")


def test_eurostat_uses_verified_certificate_context(monkeypatch):
    seen = {}
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"value":{}}'
    def open_url(request, **kwargs):
        seen.update(kwargs)
        return Response()
    monkeypatch.setattr(source_eurostat_air, "urlopen", open_url)
    assert source_eurostat_air.fetch_json("https://ec.europa.eu/test") == {"value": {}}
    assert seen["context"].check_hostname
    assert seen["context"].verify_mode == 2


def test_google_429_retries_same_session(monkeypatch):
    calls = []
    def get(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=429 if len(calls) == 1 else 200,
                               headers={"Retry-After": "1"}, text=')]}\'\n{"widgets":[]}',
                               raise_for_status=lambda: None)
    delays = []
    monkeypatch.setattr(source_employment.time, "sleep", delays.append)
    session = SimpleNamespace(get=get)
    assert source_employment._google_request_json("url", params={}, session=session) == {"widgets": []}
    assert len(calls) == 2
    assert delays == [1]
