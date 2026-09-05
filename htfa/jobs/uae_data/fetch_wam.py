"""Fetch and archive the public source pages referenced by the WAM registry.

The daily event registry remains a reviewed, auditable input file.  This module
does not infer weapon counts from prose: it archives the cited pages and writes
a manifest so that the numerical processing step can be rerun offline without
silently changing historical observations.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .paths import DATA_DIR


RAW_DIR = DATA_DIR / "raw" / "wam"
DAILY_PATH = RAW_DIR / "uae_military_strike_intensity_daily.csv"
ASSET_PATH = RAW_DIR / "asset_sources.csv"
MANIFEST_PATH = RAW_DIR / "source_manifest.json"
ARCHIVE_DIR = RAW_DIR / "sources"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _source_urls() -> list[str]:
    """Return unique HTTP(S) URLs from the daily and supplementary registries."""

    urls: set[str] = set()
    with DAILY_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            for field in ("source_url", "source_url_2"):
                value = (row.get(field) or "").strip()
                if value:
                    urls.add(value)
    if ASSET_PATH.is_file():
        with ASSET_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                value = (row.get("source_url") or "").strip()
                if value:
                    urls.add(value)
    return sorted(urls)


def _archive_name(url: str) -> str:
    """Create a stable filesystem name without exposing URL punctuation."""

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    host = urlparse(url).netloc.replace(".", "_") or "unknown_host"
    return f"{host}_{digest}.html"


def _fetch(url: str) -> tuple[int | None, str, bytes | None, str | None]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    try:
        with urlopen(request, timeout=45) as response:
            body = response.read()
            return response.status, response.headers.get("Content-Type", ""), body, None
    except HTTPError as exc:
        return exc.code, "", None, f"HTTP {exc.code}: {exc.reason}"
    except (OSError, URLError) as exc:
        return None, "", None, str(exc)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".tmp", delete=False, dir=path.parent
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def refresh_source_manifest(*, force: bool = False) -> dict[str, int]:
    """Download cited pages and write a reproducible local source manifest.

    Download failures are recorded per URL and do not discard the reviewed
    numerical registry.  ``source_wam.update`` reports the failures explicitly.
    """

    if not DAILY_PATH.is_file():
        raise FileNotFoundError(f"WAM daily registry not found: {DAILY_PATH}")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    previous: dict[str, dict] = {}
    if MANIFEST_PATH.is_file():
        try:
            previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get(
                "sources", {}
            )
        except (OSError, json.JSONDecodeError):
            previous = {}

    manifest: dict[str, dict] = {}
    counts = {"total": 0, "downloaded": 0, "reused": 0, "failed": 0}
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for url in _source_urls():
        counts["total"] += 1
        archive_path = ARCHIVE_DIR / _archive_name(url)
        old = previous.get(url, {})
        if not force and archive_path.is_file() and old.get("status") == 200:
            manifest[url] = {**old, "archive_path": str(archive_path.relative_to(RAW_DIR))}
            counts["reused"] += 1
            continue
        status, content_type, body, error = _fetch(url)
        entry = {
            "url": url,
            "retrieved_at_utc": retrieved_at,
            "status": status,
            "content_type": content_type,
            "archive_path": str(archive_path.relative_to(RAW_DIR)) if body else None,
            "sha256": hashlib.sha256(body).hexdigest() if body else None,
            "error": error,
        }
        if body is not None and status == 200:
            archive_path.write_bytes(body)
            counts["downloaded"] += 1
        else:
            counts["failed"] += 1
        manifest[url] = entry

    _write_json(
        MANIFEST_PATH,
        {
            "retrieved_at_utc": retrieved_at,
            "registry": str(DAILY_PATH.relative_to(RAW_DIR.parent.parent)),
            "sources": manifest,
        },
    )
    return counts


if __name__ == "__main__":
    print(refresh_source_manifest())
