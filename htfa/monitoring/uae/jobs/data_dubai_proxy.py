"""Optional, source-scoped egress for the public Data Dubai download protocol."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROXY_KEY = "HTFA_DATA_DUBAI_PROXY_URL"
SOURCES = frozenset({"ded", "dld", "dubai_customs_air"})
CDN_HOST = "cdn.data.dubai"


def worker_environment(source: str, environment: dict) -> dict:
    """Configure only the three download workers; keep the signed-file CDN direct."""
    result = dict(environment)
    proxy = result.pop(PROXY_KEY, "").strip()
    if source not in SOURCES or not proxy:
        return result
    try:
        parsed = urlsplit(proxy)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                 and parsed.path in {"", "/"} and not parsed.query
                 and not parsed.fragment and parsed.port != 0
                 and not any(ord(char) < 32 for char in unquote(proxy)))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{PROXY_KEY} must contain a valid HTTP/HTTPS proxy URL")
    for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        result[key] = proxy
    bypass = []
    for key in ("NO_PROXY", "no_proxy"):
        for entry in result.get(key, "").split(","):
            entry = entry.strip()
            if not entry or entry.lower().lstrip(".") in {
                "*", "data.dubai", "data.dubai:443", "data.dubai:80",
            }:
                continue
            if entry not in bypass:
                bypass.append(entry)
    if CDN_HOST not in bypass:
        bypass.append(CDN_HOST)
    result["NO_PROXY"] = result["no_proxy"] = ",".join(bypass)
    return result


def redact(text: str, proxy: str) -> str:
    """Remove the configured URL, decoded userinfo and Basic proxy credentials."""
    if not proxy:
        return text
    secrets = {proxy, unquote(proxy)}
    try:
        parsed = urlsplit(proxy)
        if parsed.username is not None:
            userinfo = f"{parsed.username}:{parsed.password or ''}"
            decoded = unquote(userinfo)
            secrets.update({userinfo, decoded, base64.b64encode(decoded.encode()).decode()})
    except ValueError:
        pass
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[REDACTED_PROXY]")
    return text


def redact_result(value, proxy: str):
    """Redact result strings without changing field names or status semantics."""
    if isinstance(value, str):
        return redact(value, proxy)
    if isinstance(value, dict):
        return {key: redact_result(item, proxy) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_result(item, proxy) for item in value]
    return value


def verify() -> dict:
    """Verify live manifests and a direct signed-CDN range, without writing data."""
    from urllib.request import Request, proxy_bypass, urlopen
    from . import source_ded, source_dld, download_dubai_customs_air

    proxy = os.environ.get(PROXY_KEY, "").strip()
    if not proxy:
        raise ValueError(f"Missing repository Secret {PROXY_KEY}")
    environment = worker_environment("ded", dict(os.environ))
    # This CLI is a dedicated process: its environment is never reused by the
    # publisher or by another source worker.
    os.environ.clear()
    os.environ.update(environment)
    results = {}
    plans = [
        ("ded", lambda: source_ded.fetch_data_dubai_files(
            source_ded.build_opener(), source_ded.DATASET_ID)),
        ("dld", lambda: source_dld._get_bulk_csv_files(
            source_dld.TRANSACTIONS_DATASET_ID, source_dld.TRANSACTIONS_DATASET_PAGE)),
        ("dubai_customs_air", lambda: download_dubai_customs_air.csv_files_of(
            download_dubai_customs_air.fetch_manifest_pages(459114))),
    ]
    for name, fetch in plans:
        try:
            files = fetch()
            if not files:
                raise ValueError("Official download manifest is empty")
            url = files[0]["file_url"]
            if (urlsplit(url).scheme != "https" or urlsplit(url).hostname != CDN_HOST
                    or not proxy_bypass(CDN_HOST)):
                raise ValueError("CDN direct route was not verified")
            request = Request(url, headers={"Range": "bytes=0-1023"})
            with urlopen(request, timeout=60) as response:
                block = response.read(1024)
                if response.status not in {200, 206} or not block:
                    raise ValueError("CDN range download failed")
                if files[0]["file_name"].endswith(".gz") and not block.startswith(b"\x1f\x8b"):
                    raise ValueError("CDN did not return the advertised gzip file")
            results[name] = {"status": "ok", "manifest_files": len(files),
                             "direct_cdn_bytes": len(block)}
        except Exception as exc:
            # Signed file URLs and proxy credentials must not enter artifacts.
            results[name] = {"status": "error", "error_type": type(exc).__name__}
    return {"status": "ok" if all(r["status"] == "ok" for r in results.values()) else "error",
            "sources": results}


def main() -> None:
    try:
        result = verify()
    except ValueError as exc:
        result = {"status": "error", "error": str(exc)}
    output = Path(os.environ["RUNNER_TEMP"]) / "data-dubai-proxy-verification.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
