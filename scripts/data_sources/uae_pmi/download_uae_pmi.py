"""Download the public sample of the S&P Global UAE headline PMI.

Trading Economics publicly displays a licensed, limited sample of the UAE
headline PMI.  Its chart configuration is read from the public indicator page
at run time, so no account credential or private API key is required.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import html
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen


PUBLIC_PAGE_URL = (
    "https://tradingeconomics.com/united-arab-emirates/manufacturing-pmi"
)
SP_GLOBAL_RELEASES_URL = (
    "https://www.pmi.spglobal.com/Public/Release/PressReleases"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CONFIG_FIELDS = (
    "TEChartsDatasource",
    "TEChartsToken",
    "TEObfuscationkey",
    "TESymbol",
    "TELastUpdate",
)


def fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    """Fetch one public URL with a bounded timeout."""

    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} while downloading {url}")
        return response.read()


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    """Fetch one UTF-8-compatible public page."""

    return fetch_bytes(url, headers).decode("utf-8", errors="replace")


def parse_chart_config(page_html: str) -> dict[str, str]:
    """Extract the chart endpoint configuration embedded in the public page."""

    config: dict[str, str] = {}
    for field in CONFIG_FIELDS:
        match = re.search(
            rf"\b{re.escape(field)}\s*=\s*['\"]([^'\"]+)['\"]",
            page_html,
        )
        if match:
            config[field] = html.unescape(match.group(1)).strip()
    required = set(CONFIG_FIELDS) - {"TELastUpdate"}
    missing = sorted(required - config.keys())
    if missing:
        raise ValueError(
            "Public chart configuration is incomplete: " + ", ".join(missing)
        )
    return config


def decode_chart_response(response_body: bytes, xor_key: str) -> Any:
    """Decode the chart response using the algorithm published by its web app."""

    text = response_body.decode("ascii").strip()
    try:
        encoded = json.loads(text)
    except json.JSONDecodeError:
        encoded = text.strip('"')
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Unexpected public chart response envelope")
    try:
        compressed = bytearray(base64.b64decode(encoded, validate=True))
    except (ValueError, TypeError) as exc:
        raise ValueError("Public chart response is not valid base64") from exc
    key = xor_key.encode("utf-8")
    if not key:
        raise ValueError("Public chart XOR key is blank")
    for index in range(len(compressed)):
        compressed[index] ^= key[index % len(key)]
    try:
        decoded = gzip.decompress(bytes(compressed))
    except OSError as exc:
        raise ValueError("Public chart response is not valid gzip data") from exc
    try:
        return json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Public chart payload is not valid JSON") from exc


def extract_series(payload: Any) -> dict[str, Any]:
    """Return and validate the single UAE PMI series from a chart payload."""

    try:
        series = payload[0]["series"][0]["serie"]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError("UAE PMI series was not found in chart payload") from exc
    required = {"data", "source", "frequency", "country", "unit"}
    missing = sorted(required - series.keys())
    if missing:
        raise ValueError("UAE PMI series metadata is incomplete: " + ", ".join(missing))
    if series["country"] != "United Arab Emirates":
        raise ValueError(f"Unexpected chart country: {series['country']!r}")
    if str(series["frequency"]).lower() != "monthly":
        raise ValueError(f"Unexpected chart frequency: {series['frequency']!r}")
    if "S&P" not in str(series["source"]):
        raise ValueError(f"Unexpected chart source: {series['source']!r}")
    if not isinstance(series["data"], list) or not series["data"]:
        raise ValueError("UAE PMI chart contains no observations")
    return series


def find_latest_official_release(index_html: str) -> dict[str, str] | None:
    """Find the current English UAE PMI release in S&P Global's public index."""

    block_pattern = re.compile(
        r'<div\s+class="listItem">(?P<body>.*?)</div>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in block_pattern.finditer(index_html):
        body = match.group("body")
        title_match = re.search(
            r'<span\s+class="releaseTitle">(.*?)</span>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not title_match:
            continue
        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        if title != "S&P Global United Arab Emirates PMI":
            continue
        date_match = re.search(
            r'<span\s+class="releaseDate">(.*?)</span>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        url_match = re.search(r'href="([^"]+)"', body, flags=re.IGNORECASE)
        if not date_match or not url_match:
            return None
        release_date = re.sub(r"<[^>]+>", "", date_match.group(1))
        release_date = " ".join(html.unescape(release_date).split())
        return {
            "title": title,
            "release_date_utc": release_date,
            "url": urljoin(SP_GLOBAL_RELEASES_URL, html.unescape(url_match.group(1))),
        }
    return None


def atomic_json_dump(path: Path, payload: Any) -> None:
    """Write JSON atomically so a failed refresh cannot truncate prior data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def download(output_dir: Path) -> tuple[Path, Path]:
    """Download the public chart sample and its provenance metadata."""

    page_html = fetch_text(PUBLIC_PAGE_URL)
    config = parse_chart_config(page_html)
    chart_url = (
        config["TEChartsDatasource"].rstrip("/")
        + "/economics/"
        + config["TESymbol"].lower()
        + "?span=max"
    )
    chart_body = fetch_bytes(
        chart_url,
        headers={"x-api-key": config["TEChartsToken"]},
    )
    payload = decode_chart_response(chart_body, config["TEObfuscationkey"])
    series = extract_series(payload)

    official_release = None
    try:
        official_release = find_latest_official_release(
            fetch_text(SP_GLOBAL_RELEASES_URL)
        )
    except (OSError, RuntimeError):
        # The chart download remains usable if the optional release-index
        # cross-check is temporarily unavailable.
        official_release = None

    raw_path = output_dir / "tradingeconomics_chart.json"
    metadata_path = output_dir / "source_metadata.json"
    atomic_json_dump(raw_path, payload)
    atomic_json_dump(
        metadata_path,
        {
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "indicator": "S&P Global UAE headline PMI",
            "definition": (
                "UAE non-oil private-sector headline PMI, seasonally adjusted"
            ),
            "original_source": series["source"],
            "public_display_provider": "Trading Economics",
            "public_page_url": PUBLIC_PAGE_URL,
            "chart_url": chart_url,
            "chart_symbol": config["TESymbol"],
            "source_last_update": config.get("TELastUpdate"),
            "observation_count": len(series["data"]),
            "first_reference_date": series["data"][0][3],
            "last_reference_date": series["data"][-1][3],
            "latest_value": series["data"][-1][0],
            "official_release_index_url": SP_GLOBAL_RELEASES_URL,
            "latest_official_release": official_release,
            "coverage_note": (
                "Trading Economics labels this as a limited sample licensed from "
                "S&P Global. Full headline history and sub-indices require a "
                "subscription; this downloader does not claim full survey history."
            ),
        },
    )
    return raw_path, metadata_path


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "data" / "UAE_PMI" / "raw",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_path, metadata_path = download(args.output_dir.resolve())
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    print(f"Downloaded {metadata['observation_count']} UAE PMI observations")
    print(
        f"Coverage: {metadata['first_reference_date']} through "
        f"{metadata['last_reference_date']}; latest={metadata['latest_value']}"
    )
    print(f"Raw data: {raw_path}")
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
