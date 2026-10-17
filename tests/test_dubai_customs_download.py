"""Checks for resumable, complete official customs shard downloads."""

import gzip
from io import BytesIO

import pytest

from htfa.jobs.uae_data import download_dubai_customs_air as downloader


class Response(BytesIO):
    def __init__(self, payload, status=200, headers=None):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {"Content-Length": str(len(payload))}


def test_download_resumes_partial_gzip(monkeypatch, tmp_path):
    payload = gzip.compress(b"source records" * 100)
    target = tmp_path / "shard.csv.gz"
    partial = target.with_suffix(".gz.part")
    offset = len(payload) // 2
    partial.write_bytes(payload[:offset])
    requests = []
    def open_url(request, **kwargs):
        requests.append(request)
        return Response(payload[offset:], 206, {
            "Content-Length": str(len(payload) - offset),
            "Content-Range": f"bytes {offset}-{len(payload)-1}/{len(payload)}",
        })
    monkeypatch.setattr(downloader, "urlopen", open_url)
    assert downloader.download_file("https://example.com/shard", target) == "ok"
    assert requests[0].get_header("Range") == f"bytes={offset}-"
    assert target.read_bytes() == payload
    assert not partial.exists()


def test_server_without_range_support_restarts_partial(monkeypatch, tmp_path):
    payload = gzip.compress(b"complete records")
    target = tmp_path / "shard.csv.gz"
    target.with_suffix(".gz.part").write_bytes(b"partial")
    monkeypatch.setattr(downloader, "urlopen", lambda *a, **k: Response(payload))
    assert downloader.download_file("https://example.com/shard", target) == "ok"
    assert target.read_bytes() == payload


def test_bad_download_preserves_previous_good_file(monkeypatch, tmp_path):
    target = tmp_path / "shard.csv.gz"
    original = gzip.compress(b"previous records")
    target.write_bytes(original)
    monkeypatch.setattr(downloader, "urlopen", lambda *a, **k: Response(b"not gzip"))
    with pytest.raises(ValueError, match="CRC"):
        downloader.download_file("https://example.com/shard", target, force=True)
    assert target.read_bytes() == original
