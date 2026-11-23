"""Failures retain endpoint identity without hiding WAF pages or leaking keys."""

from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from htfa.monitoring.uae.jobs import _official_download as download
from htfa.monitoring.uae.jobs import download_dubai_customs_air as customs
from htfa.monitoring.uae.jobs import source_foreign_labour as labour


def test_browser_rate_limit_retries_same_endpoint_and_honors_retry_after(monkeypatch):
    from curl_cffi import requests

    calls = []
    delays = []
    responses = iter([
        SimpleNamespace(status_code=429, headers={"Retry-After": "7"}),
        SimpleNamespace(status_code=200, content=b"official data"),
    ])

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(download.time, "sleep", delays.append)
    assert download.fetch_bytes("https://official.test/data", browser_transport=True) == b"official data"
    assert calls[0] == calls[1]
    assert delays == [7]


@pytest.mark.parametrize("browser", [True, False])
def test_http_failure_identifies_endpoint_and_redacts_api_key(monkeypatch, capsys, browser):
    from curl_cffi import requests

    url = "https://official.test/data?api_key=private-value&frequency=daily"
    monkeypatch.setattr(requests, "get", lambda *a, **kw: SimpleNamespace(status_code=403))

    def fail(*args, **kwargs):
        raise HTTPError(url, 403, "forbidden", None, None)

    monkeypatch.setattr(download, "urlopen", fail)
    with pytest.raises(HTTPError) as error:
        download.fetch_bytes(url, browser_transport=browser)
    output = capsys.readouterr().out + str(error.value) + error.value.url
    assert "https://official.test/data" in output
    assert "frequency=daily" in output
    assert "private-value" not in output


def test_access_denial_with_http_200_is_not_treated_as_missing_token():
    with pytest.raises(RuntimeError, match="Request Rejected.*endpoint=https://data.dubai"):
        download.reject_access_page("<title>Request Rejected</title>", "https://data.dubai/en/l/1")
    download.reject_access_page("<title>Official dataset</title>", "https://data.dubai/en/l/1")


def test_customs_http_200_block_page_reports_access_denial(monkeypatch):
    response = BytesIO(b"<title>Request Rejected</title>")
    response.status = 200
    monkeypatch.setattr(customs, "urlopen", lambda *a, **kw: response)
    with pytest.raises(RuntimeError, match="rejected this collector host"):
        customs.fetch_json("https://data.dubai/o/dda/data-services/dataset-download")


def test_nepal_curl_empty_reply_retries_without_changing_session(monkeypatch):
    from curl_cffi.requests.exceptions import ConnectionError

    calls = []
    response = SimpleNamespace(content=b"%PDF data", headers={"Content-Type": "application/pdf"},
                               raise_for_status=lambda: None)

    def get(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise ConnectionError("curl: (52) Empty reply from server")
        return response

    monkeypatch.setattr(labour.time, "sleep", lambda _: None)
    assert labour.get_bytes(SimpleNamespace(get=get), "https://dofe.gov.np/report") == (
        b"%PDF data", "application/pdf",
    )
    assert calls == ["https://dofe.gov.np/report"] * 2
