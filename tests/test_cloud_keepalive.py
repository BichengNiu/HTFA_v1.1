"""Exercise the real browser against deterministic sleep and failure pages."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest
from playwright.sync_api import sync_playwright
import yaml

from scripts.cloud_keepalive import (
    APP_TITLE, KeepaliveError, safe_error, validate_url, wake_and_verify,
)

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = shutil.which("chromium")


@pytest.fixture
def server():
    state = {"wakes": 0}
    ready = f'<h1>{APP_TITLE}</h1><div data-testid="stMetricValue">2.5</div>'

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = '<h1>Zzzz</h1><button onclick="location.href=\'/ready\'">Yes, get this app back up!</button>'
            elif self.path == "/ready":
                state["wakes"] += 1
                body = ready
            elif self.path == "/frame":
                body = '<iframe src="/ready"></iframe>'
            elif self.path == "/broken":
                body = ready + '<div data-testid="stException">Database missing</div>'
            elif self.path == "/unstable":
                body = ready + '<script>setTimeout(()=>location.href="/shell",300)</script>'
            else:
                body = "<h1>Streamlit</h1><p>Loading...</p>"
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", state
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=5)


@pytest.fixture
def page():
    if not CHROMIUM:
        pytest.skip("System Chromium required for browser integration checks")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page()
        try:
            yield page
        finally:
            browser.close()


def test_sleeping_page_is_clicked_and_actual_app_is_verified(page, server):
    url, state = server
    assert wake_and_verify(page, url, timeout=5, hold_seconds=0) is True
    assert state["wakes"] == 1


def test_already_awake_app_and_embedded_app_are_verified(page, server):
    url, _ = server
    assert wake_and_verify(page, url + "/ready", timeout=5, hold_seconds=0) is False
    assert wake_and_verify(page, url + "/frame", timeout=5, hold_seconds=0) is False


def test_http_200_and_loading_shell_are_not_success(page, server):
    url, _ = server
    with pytest.raises(KeepaliveError, match="page shell is not success"):
        wake_and_verify(page, url + "/shell", timeout=1, hold_seconds=0)


def test_application_error_and_unstable_session_are_failures(page, server):
    url, _ = server
    with pytest.raises(KeepaliveError, match="application error"):
        wake_and_verify(page, url + "/broken", timeout=3, hold_seconds=0)
    with pytest.raises(KeepaliveError, match="did not remain ready"):
        wake_and_verify(page, url + "/unstable", timeout=3, hold_seconds=1)


def test_cli_preserves_failure_exit_code_and_screenshot(server, tmp_path):
    if not CHROMIUM:
        pytest.skip("System Chromium required")
    url, _ = server
    screenshot = tmp_path / "failure.png"
    result = subprocess.run([
        sys.executable, str(ROOT / "scripts/cloud_keepalive.py"), "--url", url + "/shell",
        "--timeout", "1", "--hold-seconds", "0", "--browser-executable", CHROMIUM,
        "--screenshot", str(screenshot),
    ], capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    assert "FAILED" in result.stdout
    assert "VERIFIED" not in result.stdout
    assert screenshot.is_file()


@pytest.mark.parametrize("url", [
    "http://example.streamlit.app", "https://example.com",
    "https://user:password@example.streamlit.app", "https://example.streamlit.app/?token=secret",
])
def test_only_public_streamlit_or_local_test_urls_are_accepted(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_error_logging_removes_authentication_payloads():
    message = safe_error(RuntimeError("Failed https://user:password@host.test/login?payload=secret"))
    assert message == "Failed https://host.test/login"


def test_workflow_has_margin_before_hibernation_and_empty_commits_do_not_retrigger():
    workflow = yaml.load((ROOT / ".github/workflows/streamlit-keepalive.yml").read_text(), Loader=yaml.BaseLoader)
    fields = workflow["on"]["schedule"][0]["cron"].split()
    interval = int(fields[1].removeprefix("*/"))
    assert 24 % interval == 0
    assert interval == 6
    assert interval < 12
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert set(workflow["on"]["push"]["paths"]) == {
        ".github/workflows/streamlit-keepalive.yml", "scripts/cloud_keepalive.py",
        "tooling/requirements/requirements-keepalive.txt", "scripts/cloud_refresh.py",
        "htfa/jobs/uae_data/cloud_worker.py", "htfa/jobs/uae_data/portable_workbook.py",
        "htfa/jobs/uae_data/download_uae_years.mjs",
        "htfa/jobs/uae_data/download_t100.py",
        "htfa/jobs/uae_data/source_dubai_customs_air.py",
    }
    assert workflow["permissions"]["contents"] == "write"
