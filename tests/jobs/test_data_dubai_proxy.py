"""A source-specific proxy must not redirect publication or disclose credentials."""

import base64
import json
import subprocess
from types import SimpleNamespace
from urllib.request import proxy_bypass_environment

import pytest
from requests.utils import should_bypass_proxies

from htfa.monitoring.uae.jobs import daily_refresh
from htfa.monitoring.uae.jobs.data_dubai_proxy import PROXY_KEY, worker_environment


PROXY = "http://test-user:proxy-test-password@proxy.example:8080"


@pytest.mark.parametrize("source", ["ded", "dld", "dubai_customs_air"])
def test_proxy_routes_portal_and_keeps_bulk_cdn_direct(source):
    original = {PROXY_KEY: PROXY, "NO_PROXY": "localhost,.data.dubai",
                "no_proxy": "127.0.0.1,*", "CURL_CA_BUNDLE": "trusted-ca.pem"}
    env = worker_environment(source, original)
    assert PROXY_KEY not in env
    assert env["https_proxy"] == env["HTTPS_PROXY"] == PROXY
    assert not proxy_bypass_environment("data.dubai", {"no": env["NO_PROXY"]})
    assert proxy_bypass_environment("cdn.data.dubai", {"no": env["NO_PROXY"]})
    assert not should_bypass_proxies("https://data.dubai/en/", env["NO_PROXY"])
    assert should_bypass_proxies("https://cdn.data.dubai/file.gz", env["NO_PROXY"])
    assert env["CURL_CA_BUNDLE"] == "trusted-ca.pem"
    assert original["NO_PROXY"] == "localhost,.data.dubai"


@pytest.mark.parametrize("source", ["fcsc", "cbuae", "energy", "finalize"])
def test_proxy_secret_is_not_passed_to_other_workers(source):
    assert worker_environment(source, {PROXY_KEY: PROXY, "HOME": "kept"}) == {"HOME": "kept"}


def test_unconfigured_proxy_preserves_existing_network_environment():
    original = {"HTTPS_PROXY": "http://existing:3128", "NO_PROXY": "localhost"}
    assert worker_environment("ded", original) == original


@pytest.mark.parametrize("proxy", ["socks5://secret@host:1080", "http://", "http://host:70000",
                                  "http://host:8080/?password=secret", "http://host:8080/%0a"])
def test_invalid_proxy_fails_without_echoing_value(proxy):
    with pytest.raises(ValueError) as error:
        worker_environment("ded", {PROXY_KEY: proxy})
    assert proxy not in str(error.value)


def test_source_worker_and_artifacts_redact_proxy_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv(PROXY_KEY, PROXY)
    monkeypatch.setenv("GH_TOKEN", "release-token")
    captured = []
    basic = base64.b64encode(b"test-user:proxy-test-password").decode()

    def run(command, **kwargs):
        captured.append(kwargs["env"])
        kwargs["stdout"].write(f"provider error at {PROXY}; Proxy-Authorization: Basic {basic}")
        (tmp_path / "ded.json").write_text(json.dumps({"status": "ok", "note": PROXY}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(daily_refresh.subprocess, "run", run)
    result = daily_refresh.run_worker("ded", tmp_path, tmp_path)
    assert result["status"] == "ok"
    assert captured[0]["HTTPS_PROXY"] == PROXY
    assert "GH_TOKEN" not in captured[0]
    assert PROXY_KEY not in captured[0]
    artifacts = str(result) + (tmp_path / "ded.log").read_text() + (tmp_path / "ded.json").read_text()
    assert PROXY not in artifacts
    assert "proxy-test-password" not in artifacts
    assert basic not in artifacts


def test_timed_out_worker_still_scrubs_log(monkeypatch, tmp_path):
    monkeypatch.setenv(PROXY_KEY, PROXY)

    def run(command, **kwargs):
        kwargs["stdout"].write(PROXY)
        kwargs["stdout"].flush()
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(daily_refresh.subprocess, "run", run)
    result = daily_refresh.run_worker("dld", tmp_path, tmp_path, timeout=1)
    assert result["status"] == "error"
    assert PROXY not in (tmp_path / "dld.log").read_text()


def test_invalid_source_proxy_is_an_isolated_source_failure(monkeypatch, tmp_path):
    monkeypatch.setenv(PROXY_KEY, "invalid-private-proxy")
    result = daily_refresh.run_worker("ded", tmp_path, tmp_path)
    assert result["status"] == "error"
    assert "invalid-private-proxy" not in str(result)
