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


def _client_hello_template(context, host: str) -> str:
    """Fingerprint a fresh TLS 1.2 ClientHello after masking random/session bytes."""
    import hashlib
    import ssl

    outgoing = ssl.MemoryBIO()
    client = context.wrap_bio(ssl.MemoryBIO(), outgoing, server_hostname=host)
    try:
        client.do_handshake()
    except ssl.SSLWantReadError:
        pass
    hello = bytearray(outgoing.read())
    if len(hello) < 44 or hello[0] != 22 or hello[5] != 1:
        raise ValueError("Expected a TLS ClientHello record")
    hello[11:43] = bytes(32)
    session_length = hello[43]
    hello[44:44 + session_length] = bytes(session_length)
    return hashlib.sha256(hello).hexdigest()


def diagnose_network() -> None:
    """Compare DNS, verified TLS and identical anonymous HTTP request bytes."""
    import hashlib
    import http.client
    import importlib.metadata
    import socket
    import ssl
    import sys

    host = "data.dubai"
    context = ssl.create_default_context()
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers("ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256")
    print(json.dumps({"python": sys.version.split()[0], "openssl": ssl.OPENSSL_VERSION,
                      "curl_cffi": importlib.metadata.version("curl_cffi"),
                      "dns": sorted({a[4][0] for a in socket.getaddrinfo(
                          host, 443, type=socket.SOCK_STREAM)}),
                      "client_hello_template_sha256": _client_hello_template(context, host),
                      "proxy_env_names": [k for k in os.environ if k.upper().endswith("_PROXY")]}), flush=True)
    trace = requests.get("https://www.cloudflare.com/cdn-cgi/trace", timeout=30)
    fields = dict(line.split("=", 1) for line in trace.text.splitlines() if "=" in line)
    print(json.dumps({"public_network": {k: fields.get(k) for k in ("ip", "loc", "colo")}}), flush=True)
    ipv4 = requests.get("https://api.ipify.org?format=json", timeout=30).json().get("ip")
    info = requests.get("https://stat.ripe.net/data/network-info/data.json",
                        params={"resource": ipv4}, timeout=30).json().get("data", {})
    print(json.dumps({"public_ipv4": ipv4, "asns": info.get("asns"),
                      "prefix": info.get("prefix")}), flush=True)
    for path in ["/", *[
        f"/o/dda/data-services/dataset-download?datasetId={identifier}&page=1&pageSize=30&sortDir=desc"
        for identifier in (460521, 470061, 459114)
    ]]:
        # Send the same byte sequence on both hosts, with no cookie, token,
        # browser impersonation or automatic proxy configuration.
        request = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                   "User-Agent: HTFA/1.1 data-source-diagnostic\r\n"
                   "Accept: application/json\r\nAccept-Encoding: identity\r\n"
                   "Connection: close\r\n\r\n").encode("ascii")
        result = {"path": path, "request_sha256": hashlib.sha256(request).hexdigest()}
        connection = http.client.HTTPSConnection(host, context=context, timeout=45)
        try:
            connection.connect()
            result.update(peer_ip=connection.sock.getpeername()[0], tls=connection.sock.version(),
                          cipher=connection.sock.cipher()[0],
                          certificate_sha256=hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest())
            connection.sock.sendall(request)
            response = http.client.HTTPResponse(connection.sock)
            response.begin()
            payload = response.read(1024 * 1024 + 1)
            text_body = payload.decode("utf-8", errors="replace")
            title = re.search(r"<title[^>]*>(.*?)</title>", text_body, re.I | re.S)
            support = re.search(r"support\s+ID\s+is:\s*([^<\s]+)", text_body, re.I)
            result.update(http_status=response.status, bytes=len(payload),
                          title=title.group(1) if title else None,
                          response_sha256=hashlib.sha256(payload).hexdigest(),
                          support_id=support.group(1) if support else None,
                          cookie_names=[value.split("=", 1)[0] for key, value in response.getheaders()
                                        if key.lower() == "set-cookie"],
                          headers={key: response.getheader(key) for key in (
                              "Content-Type", "Content-Length", "Server", "Via", "CF-Ray",
                              "CF-Cache-Status", "X-Cache", "X-Content-Type-Options")})
        except Exception as exc:
            result["error_type"] = type(exc).__name__
        finally:
            connection.close()
        print(json.dumps(result), flush=True)


def main() -> None:
    """Probe each institution with bounded concurrency and report all failures."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-updates", action="store_true")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--data-dubai", action="store_true")
    parser.add_argument("--network", action="store_true")
    args = parser.parse_args()
    if args.network:
        diagnose_network()
        return
    if args.data_dubai:
        from .verify_data_dubai_access import DATASET_URLS

        # Follow the public portal's entry/session and its documented JS calls.
        # Response bodies and signed download URLs are deliberately not logged.
        with requests.Session(impersonate="chrome") as session:
            for name, url in [
                ("portal home", "https://data.dubai/"),
                ("English home", "https://data.dubai/en/"),
                ("Arabic home", "https://data.dubai/ar/"),
            ]:
                response = session.get(url, timeout=45)
                print(json.dumps({"test": name, "status": response.status_code,
                                  "bytes": len(response.content),
                                  "blocked": "Request Rejected" in response.text}), flush=True)
            for name, identifier in [("DED", 460521), ("DLD", 470061), ("Customs", 459114)]:
                source = {460521: "ded", 470061: "dld", 459114: "dubai_customs_air"}[identifier]
                gateway = session.get(DATASET_URLS[source], params={"limit": 1},
                                      headers={"Accept": "application/json"}, timeout=45)
                print(json.dumps({"test": name + " official API gateway without credentials",
                                  "status": gateway.status_code,
                                  "content_type": gateway.headers.get("Content-Type")}), flush=True)
                page_url = f"https://data.dubai/en/l/{identifier}"
                page = session.get(page_url, timeout=45)
                token = re.search(r"Liferay\.authToken\s*=\s*['\"]([^'\"]+)", page.text)
                print(json.dumps({"test": name + " session page", "status": page.status_code,
                                  "bytes": len(page.content), "csrf": bool(token)}), flush=True)
                headers = {"Accept": "application/json", "Content-Type": "application/json",
                           "Referer": page_url}
                if token:
                    headers["X-CSRF-Token"] = token.group(1)
                for kind, query in [
                    ("dataset-download", f"datasetId={identifier}&page=1&pageSize=10&sortDir=desc"),
                    ("dataset-download", f"datasetId={identifier}&page=1&pageSize=10&sortDir=desc&format=json"),
                    ("dataset-metadata", f"datasetId={identifier}&download=true"),
                    ("dataset-metadata", f"datasetId={identifier}&cacheCheck=true"),
                ]:
                    response = session.get("https://data.dubai/o/dda/data-services/" + kind + "?" + query,
                                           headers=headers, timeout=45)
                    result = {"test": name + " " + kind + " " + query.split("&")[-1],
                              "status": response.status_code, "bytes": len(response.content),
                              "content_type": response.headers.get("Content-Type"),
                              "blocked": "Request Rejected" in response.text}
                    try:
                        payload = response.json()
                        result["success"] = payload.get("success")
                        data = payload.get("data") or {}
                        result["data_keys"] = list(data) if isinstance(data, dict) else []
                    except ValueError:
                        pass
                    print(json.dumps(result), flush=True)
        return
    if args.browser:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not bool(os.environ.get("DISPLAY")))
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
