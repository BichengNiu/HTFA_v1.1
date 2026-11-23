"""Inspect public source responses on the collector host without changing data."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
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
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(probe, endpoint_plans()))


if __name__ == "__main__":
    main()
