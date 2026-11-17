"""Transport interruption must not invalidate a good LFS publication forever."""

import hashlib

import pytest
import requests

from htfa.monitoring.uae.jobs import verify_publication as verifier


class Response:
    def __init__(self, blocks, *, status=200, content_range=None):
        self.blocks = blocks
        self.status_code = status
        self.headers = {"Content-Range": content_range} if content_range else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, size):
        for block in self.blocks:
            if isinstance(block, Exception):
                raise block
            yield block


@pytest.mark.parametrize("range_supported", [True, False])
def test_interruption_resumes_or_restarts_without_corrupt_hash(monkeypatch, range_supported):
    content = b"complete validated database"
    calls = []
    monkeypatch.setattr(verifier.time, "sleep", lambda seconds: None)

    def get(url, *, headers, **kwargs):
        calls.append(headers)
        if len(calls) == 1:
            return Response([content[:8], requests.exceptions.ChunkedEncodingError("interrupted")])
        assert headers == {"Range": "bytes=8-"}
        if range_supported:
            return Response([content[8:]], status=206, content_range=f"bytes 8-{len(content)-1}/{len(content)}")
        return Response([content])

    monkeypatch.setattr(verifier.requests, "get", get)
    result = verifier.verify_object("https://example.org/data", hashlib.sha256(content).hexdigest(), len(content))
    assert result["status"] == "verified"
    assert result["bytes"] == len(content)
    assert result["attempts"] == 2


def test_wrong_range_is_rejected_before_appending(monkeypatch):
    content = b"abcdef"
    count = 0
    monkeypatch.setattr(verifier.time, "sleep", lambda seconds: None)

    def get(url, *, headers, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return Response([b"abc"])
        if count == 2:
            return Response([b"def"], status=206, content_range="bytes 2-4/6")
        assert headers == {}
        return Response([content])

    monkeypatch.setattr(verifier.requests, "get", get)
    result = verifier.verify_object("https://example.org/data", hashlib.sha256(content).hexdigest(), len(content))
    assert result["attempts"] == 3


def test_corrupt_remote_object_never_passes(monkeypatch):
    monkeypatch.setattr(verifier.time, "sleep", lambda seconds: None)
    calls = []
    monkeypatch.setattr(verifier.requests, "get", lambda *a, **k: (calls.append(1) or Response([b"wrong"])))
    with pytest.raises(RuntimeError, match="failed after 4 attempts.*SHA256"):
        verifier.verify_object("https://example.org/data", hashlib.sha256(b"right").hexdigest(), 5)
    assert len(calls) == 4


def test_ref_is_resolved_before_reading_pointer_and_remote(monkeypatch):
    revision = "a" * 40
    content = b"valid"
    digest = hashlib.sha256(content).hexdigest()
    pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{digest}\nsize 5\n"
    seen = []

    def command(args, **kwargs):
        seen.append(args)
        return revision + "\n" if args[1] == "rev-parse" else pointer

    def get(url, **kwargs):
        assert f"/{revision}/htfa/monitoring/uae/assets/uae.duckdb" in url
        return Response([content])

    monkeypatch.setattr(verifier.subprocess, "check_output", command)
    monkeypatch.setattr(verifier.requests, "get", get)
    assert verifier.verify("main")["commit"] == revision
    assert seen[1][2] == f"{revision}:htfa/monitoring/uae/assets/uae.duckdb"
