"""Wake the public HTFA app and verify rendered application content.

This does not treat a successful HTTP response, an empty page, or the Streamlit
shell as success. TLS verification remains enabled. No cookies or browser
storage are saved, and failure artifacts contain only a screenshot.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Error, TimeoutError, sync_playwright

APP_URL = "https://fyjpjytbgdretgzufqnxte.streamlit.app/"
APP_TITLE = "阿联酋经济监测"
WAKE_BUTTON = re.compile(r"get this app back up|wake (?:it|this app) (?:back )?up|唤醒", re.I)


class KeepaliveError(RuntimeError):
    """The application could not be confirmed as awake and functional."""


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    local_test = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    public_app = parsed.scheme == "https" and (parsed.hostname or "").endswith(".streamlit.app")
    if not (local_test or public_app) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL must be a public HTTPS Streamlit app or a local test server")
    return url


def page_status(page):
    """Check every frame; an app title and rendered metric are both required."""
    sleeping_button = None
    ready = False
    for frame in list(page.frames):
        if frame.is_detached():
            continue
        try:
            for selector in ('[data-testid="stException"]', '[data-testid="stAlertContentError"]'):
                if frame.locator(selector).first.is_visible():
                    raise KeepaliveError("HTFA rendered an application error")
            title = frame.get_by_role("heading", name=APP_TITLE, exact=True)
            metric = frame.locator('[data-testid="stMetricValue"]')
            if title.first.is_visible() and metric.first.is_visible():
                ready = True
            button = frame.get_by_role("button", name=WAKE_BUTTON).first
            if button.is_visible():
                sleeping_button = button
        except Error:
            if not frame.is_detached():
                raise
    if ready:
        return "ready", None
    if sleeping_button is not None:
        return "sleeping", sleeping_button
    return "loading", None


def wake_and_verify(page, url=APP_URL, *, timeout=180, hold_seconds=15):
    """Click the sleep page once, then require real HTFA content and a stable session."""
    validate_url(url)
    deadline = time.monotonic() + timeout
    woke = False
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=min(timeout * 1000, 45000))
    except TimeoutError:
        print("Navigation is slow; checking for rendered content", flush=True)
    previous_status = None
    while time.monotonic() < deadline:
        status, button = page_status(page)
        if status != previous_status:
            print(f"Browser status: {status}", flush=True)
            previous_status = status
        if status == "sleeping" and not woke:
            print("Clicking Streamlit wake button", flush=True)
            button.click(timeout=15000)
            woke = True
        elif status == "ready":
            if hold_seconds:
                page.wait_for_timeout(hold_seconds * 1000)
            if page_status(page)[0] != "ready":
                raise KeepaliveError("HTFA did not remain ready during session verification")
            print("VERIFIED: HTFA heading and metric rendered; session remained active", flush=True)
            return woke
        page.wait_for_timeout(min(1000, max(1, (deadline - time.monotonic()) * 1000)))
    raise KeepaliveError("Timed out waiting for HTFA heading and metric; a page shell is not success")


def safe_error(error):
    """Keep redirect query parameters and potential login payloads out of logs."""
    def clean_url(match):
        parsed = urlsplit(match.group())
        return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
    return re.sub(r"https?://[^\s\"'<>]+", clean_url, str(error))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=APP_URL)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--hold-seconds", type=float, default=15)
    parser.add_argument("--browser-executable")
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args(argv)
    validate_url(args.url)
    if args.timeout <= 0 or args.hold_seconds < 0:
        parser.error("timeout must be positive and hold-seconds must be nonnegative")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser_executable)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            wake_and_verify(page, args.url, timeout=args.timeout, hold_seconds=args.hold_seconds)
            return 0
        except Exception as error:
            print(f"FAILED: {type(error).__name__}: {safe_error(error)}", flush=True)
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                try:
                    page.screenshot(path=str(args.screenshot), full_page=False, timeout=10000)
                except Error:
                    print("Failure screenshot unavailable", flush=True)
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
