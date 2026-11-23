"""Inspect public source responses on the collector host without changing data."""

from __future__ import annotations

import json
import argparse
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from curl_cffi import requests


def endpoint_plans() -> list[tuple[str, str, dict]]:
    """Return public URLs and request options; never include private credentials."""
    from . import source_fcsc, source_foreign_labour, source_oil, source_public_market

    plans = [
        ("EIA API (public demo)", source_oil.EIA_BRENT_API_URL + "?" + urlencode({
            "api_key": "DEMO_KEY", "frequency": "daily", "data[0]": "value",
            "facets[series][]": "RBRTE", "length": 1,
        }), {}),
        ("EIA XLS", source_oil.EIA_BRENT_XLS_URL, {}),
        ("IMF PCPS", source_oil.IMF_DUBAI_API_URL, {}),
        ("OPEC MOMR", source_oil.OPEC_MOMR_HOME_URL, {}),
        ("FCSC CPI", source_fcsc.DATA_URL, {"headers": {
            "Accept": source_fcsc.ACCEPT_CSV, "Referer": source_fcsc.EXPLORER_URL,
        }}),
        ("Nepal DoFE", source_foreign_labour.DOFE_MONTHLY_URL, {}),
        ("Bangladesh OEP", source_foreign_labour.BMET_OEP_URL, {}),
        ("CBUAE EIBOR", source_public_market.EIBOR_URL, {}),
        ("CBUAE FX", source_public_market.FX_PAGE, {}),
        ("DFM", source_public_market.DFM_PAGE, {}),
        ("ADX", source_public_market.ADX_PAGE, {}),
        ("NY Fed EFFR", source_public_market.EFFR_BASE
         + f"?startDate=2023-01-01&endDate={date.today()}", {}),
    ]
    for name, identifier in [("DED", 460521), ("DLD", 470061), ("Customs", 459114)]:
        plans.extend([
            (f"{name} page", f"https://data.dubai/en/l/{identifier}", {}),
            (f"{name} manifest", "https://data.dubai/o/dda/data-services/"
             f"dataset-download?datasetId={identifier}&page=1&pageSize=30&sortDir=desc", {}),
        ])
    return plans


def probe(plan: tuple[str, str, dict]) -> dict:
    """Inspect one response without logging bodies, tokens or signed file URLs."""
    name, url, options = plan
    result = {"source": name, "endpoint": urlsplit(url)._replace(query="").geturl()}
    try:
        response = requests.get(url, impersonate="chrome", timeout=45, **options)
        title = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.I | re.S)
        result.update({
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "bytes": len(response.content),
            "server": response.headers.get("Server", ""),
            "title": " ".join(title.group(1).split())[:160] if title else None,
            "csrf_present": bool(re.search(r"Liferay\.authToken\s*=", response.text)),
            "challenge_markers": [marker for marker in (
                "Access Denied", "Request Rejected", "Incapsula", "Imperva",
                "captcha", "Just a moment", "Too Many Requests", "ROBOTS_DENIED",
            ) if marker.casefold() in response.text.casefold()],
        })
        if "json" in response.headers.get("Content-Type", ""):
            payload = response.json()
            result["json_keys"] = list(payload)[:12] if isinstance(payload, dict) else []
            if isinstance(payload, dict) and payload.get("error"):
                result["api_error"] = str(payload["error"])[:300]
    except Exception as exc:
        # Exceptions may contain query credentials. Only emit the exception class
        # and numeric curl code; the public endpoint is recorded above.
        result["error_type"] = type(exc).__name__
        code = re.search(r"curl: \((\d+)\)", str(exc))
        result["curl_code"] = int(code.group(1)) if code else None
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    """Probe each institution with bounded concurrency and report all failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-updates", action="store_true")
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    if args.browser:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context()
            page = context.new_page()
            for name, url in [
                ("Data Dubai", "https://data.dubai/en/l/470061"),
                ("Nepal PDF", "https://giwmscdnone.gov.np/media/pdf_upload/Final_merged_bbqpepk.pdf"),
            ]:
                try:
                    response = context.request.get(url, timeout=60000)
                    payload = response.body()
                    print(json.dumps({"source": name, "browser": True,
                                      "http_status": response.status, "bytes": len(payload),
                                      "pdf": payload.startswith(b"%PDF"),
                                      "blocked": b"Request Rejected" in payload}), flush=True)
                    if name == "Data Dubai":
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        print(json.dumps({"browser_page_title": page.title()}), flush=True)
                except Exception as exc:
                    print(json.dumps({"source": name, "error": str(exc)[:300]}), flush=True)
            browser.close()
        return
    if args.verify_updates:
        from htfa.monitoring.uae.contracts.paths import ASSETS_DIR
        from htfa.monitoring.uae.data.snapshot_store import REPOSITORY, ReleaseStore
        from .daily_refresh import refresh
        from .paths import DATA_DIR

        if DATA_DIR.resolve() == ASSETS_DIR.resolve():
            parser.error("Update verification requires an isolated HTFA_UAE_DATA_DIR")
        store = ReleaseStore(REPOSITORY, token=os.environ.get("GH_TOKEN"))
        snapshot = store.current()
        if snapshot is None:
            raise FileNotFoundError("No published baseline is available")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        store.download(snapshot, DATA_DIR, include_workbook=True)
        summary = refresh(
            Path(os.environ["RUNNER_TEMP"]) / "source-verification",
            sources=tuple(os.environ.get("VERIFY_SOURCES", "foreign_labour,public_market").split(",")),
            collect_energy=False,
        )
        print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)
        raise SystemExit(0 if summary["status"] == "ok" else 1)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(probe, endpoint_plans()))


if __name__ == "__main__":
    main()
