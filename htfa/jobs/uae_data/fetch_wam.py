"""Fetch and archive WAM source material used by the war-statistics pipeline.

This module discovers relevant articles from the official monthly sitemap,
downloads each article directly, and requires a valid NewsArticle JSON-LD
record before it is accepted. Retrieval or parsing errors propagate."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .paths import DATA_DIR


RAW_DIR = DATA_DIR / "raw" / "wam"
DAILY_PATH = RAW_DIR / "uae_military_strike_intensity_daily.csv"
AUTO_DAILY_PATH = RAW_DIR / "auto_daily_observations.csv"
ASSET_PATH = RAW_DIR / "asset_sources.csv"
MANIFEST_PATH = RAW_DIR / "source_manifest.json"
AUTO_ARTICLES_PATH = RAW_DIR / "auto_articles.json"
ARCHIVE_DIR = RAW_DIR / "sources"
SITEMAP_INDEX_URL = "https://www.wam.ae/sitemap.xml"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEWS_NAMESPACE = "http://www.google.com/schemas/sitemap-news/0.9"
AUTO_LOOKBACK_DAYS = 7
AUTO_START_DATE = date(2026, 2, 28)

_AUTO_TITLE_TERMS = (
    "uae air",
    "uae airspace",
    "uae air force",
    "uae air defence",
    "uae air defense",
    "uae intercept",
    "uae engage",
    "uae detect",
    "uae missile",
    "uae drone",
    "uae announces",
    "uae successfully",
    "uae responds",
    "ministry of defence",
    "ministry of defense",
)
_AUTO_WEAPON_TERMS = (
    "missile",
    "drone",
    "uav",
    "air defence",
    "air defense",
    "airspace",
    "intercept",
    "engage",
    "threat",
)


def _source_urls() -> list[str]:
    """Return unique HTTP(S) URLs from the daily and supplementary registries."""

    urls: set[str] = set()
    if DAILY_PATH.is_file():
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


def _fetch(url: str) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    with urlopen(request, timeout=45) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read()

def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload

def _latest_registry_date() -> date:
    """Return the last date already covered by reviewed or auto rows."""

    dates: list[date] = []
    for path in (DAILY_PATH, AUTO_DAILY_PATH):
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            dates.extend(
                date.fromisoformat((row.get("date") or "").strip())
                for row in csv.DictReader(handle)
                if (row.get("date") or "").strip()
            )
    if not dates:
        return AUTO_START_DATE - timedelta(days=1)
    return max(dates)


def uae_today() -> date:
    """Return the calendar date in the UAE's fixed UTC+4 timezone."""

    return (datetime.now(timezone.utc) + timedelta(hours=4)).date()


def last_complete_uae_date() -> date:
    """Return yesterday in the UAE, the latest complete daily period."""

    return uae_today() - timedelta(days=1)


def _is_auto_candidate(title: str, url: str) -> bool:
    text = f"{title} {url}".casefold()
    return any(term in text for term in _AUTO_TITLE_TERMS) and any(
        term in text for term in _AUTO_WEAPON_TERMS
    )


def _sitemap_month_urls(start: date, end: date) -> list[str]:
    status, _, body = _fetch(SITEMAP_INDEX_URL)
    if body is None or status != 200:
        raise RuntimeError(f"WAM sitemap index returned HTTP {status}")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError("WAM sitemap index is not valid XML") from exc

    result: list[str] = []
    pattern = re.compile(r"/sitemap/news/en/(\d{4})/(\d{1,2})/english\.xml$")
    for node in root.findall(f".//{{{SITEMAP_NAMESPACE}}}loc"):
        value = (node.text or "").strip()
        match = pattern.search(value)
        if not match:
            continue
        year, month = int(match.group(1)), int(match.group(2))
        if (year, month) < (start.year, start.month) or (year, month) > (
            end.year,
            end.month,
        ):
            continue
        result.append(value)
    return sorted(set(result))


def discover_auto_articles(
    *, start: date | None = None, end: date | None = None
) -> list[dict]:
    """Discover relevant English WAM articles from official monthly sitemaps."""

    end = end or uae_today()
    start = max(
        AUTO_START_DATE,
        start or (_latest_registry_date() - timedelta(days=AUTO_LOOKBACK_DAYS)),
    )
    articles: dict[str, dict] = {}
    for sitemap_url in _sitemap_month_urls(start, end):
        status, _, body = _fetch(sitemap_url)
        if body is None or status != 200:
            raise RuntimeError(f"WAM monthly sitemap returned HTTP {status}: {sitemap_url}")
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise RuntimeError(f"WAM monthly sitemap is not valid XML: {sitemap_url}") from exc
        for node in root.findall(f".//{{{SITEMAP_NAMESPACE}}}url"):
            url = (
                node.findtext(f"{{{SITEMAP_NAMESPACE}}}loc", default="")
                .strip()
            )
            title = html.unescape(
                node.findtext(
                    f"{{{NEWS_NAMESPACE}}}news/{{{NEWS_NAMESPACE}}}title",
                    default="",
                ).strip()
            )
            published = node.findtext(
                f"{{{NEWS_NAMESPACE}}}news/{{{NEWS_NAMESPACE}}}publication_date",
                default="",
            ).strip()
            last_modified = node.findtext(
                f"{{{SITEMAP_NAMESPACE}}}lastmod", default=""
            ).strip()
            if not _is_auto_candidate(title, url):
                continue
            if not url or not published:
                raise ValueError("WAM candidate sitemap record lacks URL or publication date")
            try:
                published_date = date.fromisoformat(published[:10])
            except ValueError as exc:
                raise ValueError(f"Invalid WAM sitemap publication date: {published!r}") from exc
            if not (start <= published_date <= end):
                continue
            articles[url] = {
                "url": url,
                "sitemap_title": title,
                "sitemap_published_at": published,
                "sitemap_last_modified": last_modified,
            }
    return sorted(articles.values(), key=lambda item: (item["sitemap_published_at"], item["url"]))




def _extract_news_article(dom: str) -> dict | None:
    pattern = re.compile(
        r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    for raw in pattern.findall(dom):
        try:
            payload = json.loads(raw.strip())
        except json.JSONDecodeError as exc:
            raise ValueError("WAM page contains invalid NewsArticle JSON-LD") from exc
        candidates = payload if isinstance(payload, list) else [payload]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            article_type = item.get("@type")
            if article_type == "NewsArticle" or (
                isinstance(article_type, list) and "NewsArticle" in article_type
            ):
                result = dict(item)
                for field in ("headline", "description", "articleBody"):
                    if isinstance(result.get(field), str):
                        result[field] = html.unescape(result[field])
                return result
    return None


def _archive_auto_dom(url: str, dom: str) -> str:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"auto_{_archive_name(url)}"
    path.write_text(dom, encoding="utf-8")
    return str(path.relative_to(RAW_DIR))


def _load_auto_payload(*, allow_missing: bool = False) -> dict:
    if not AUTO_ARTICLES_PATH.is_file():
        if allow_missing:
            return {"articles": {}}
        raise FileNotFoundError(f"WAM article cache not found: {AUTO_ARTICLES_PATH}")
    payload = _read_json(AUTO_ARTICLES_PATH)
    articles = payload.get("articles")
    if not isinstance(articles, dict):
        raise ValueError("WAM article cache must contain an articles object")
    for url, record in articles.items():
        if not isinstance(record, dict) or record.get("status") not in {"ok", "failed"}:
            raise ValueError(f"Invalid WAM article cache record: {url}")
    return payload

def load_auto_articles() -> list[dict]:
    """Read successful article records for offline reprocessing."""

    payload = _load_auto_payload()
    failed = [url for url, item in payload["articles"].items() if item["status"] == "failed"]
    if failed:
        raise RuntimeError("WAM article cache contains failed records: " + ", ".join(failed))
    return list(payload["articles"].values())

def cached_discovery_end() -> date:
    """Return the end of a complete cached sitemap scan or raise."""

    payload = _load_auto_payload()
    if payload.get("scan_status") != "complete":
        raise RuntimeError("WAM article cache does not contain a complete sitemap scan")
    value = payload.get("discovery_end")
    if not isinstance(value, str) or not value:
        raise ValueError("WAM article cache is missing discovery_end")
    try:
        end = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid WAM discovery_end: {value!r}") from exc
    return min(end, last_complete_uae_date())

def refresh_auto_articles(
    *,
    force: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, int]:
    """Discover, download, and validate WAM articles; propagate every failure."""

    end = end_date or uae_today()
    start = max(
        AUTO_START_DATE,
        start_date or (_latest_registry_date() - timedelta(days=AUTO_LOOKBACK_DAYS)),
    )
    discovered = discover_auto_articles(start=start, end=end)
    payload = _load_auto_payload(allow_missing=True)
    articles = payload["articles"]
    counts = {"discovered": len(discovered), "downloaded": 0, "reused": 0}
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for item in discovered:
        url = item["url"]
        old = articles.get(url, {})
        published_date = date.fromisoformat(item["sitemap_published_at"][:10])
        recently_published = published_date >= end - timedelta(days=AUTO_LOOKBACK_DAYS)
        reusable = (
            not force
            and not recently_published
            and old.get("status") == "ok"
            and old.get("sitemap_published_at") == item["sitemap_published_at"]
            and old.get("sitemap_last_modified") == item.get("sitemap_last_modified")
            and old.get("article_body")
        )
        if reusable:
            articles[url] = {**old, **item}
            counts["reused"] += 1
            continue
        status, _, raw_body = _fetch(url)
        if status != 200:
            raise RuntimeError(f"WAM article request returned HTTP {status}: {url}")
        dom = raw_body.decode("utf-8")
        article = _extract_news_article(dom)
        if not article or not isinstance(article.get("articleBody"), str) or not article["articleBody"].strip():
            raise ValueError(f"WAM article has no NewsArticle body: {url}")
        if not isinstance(article.get("headline"), str) or not article["headline"].strip():
            raise ValueError(f"WAM article has no NewsArticle headline: {url}")
        articles[url] = {
            **item,
            "retrieved_at_utc": retrieved_at,
            "status": "ok",
            "headline": article["headline"],
            "description": article.get("description"),
            "article_body": article["articleBody"],
            "date_published": article.get("datePublished"),
            "date_modified": article.get("dateModified"),
            "archive_path": _archive_auto_dom(url, dom),
            "error": None,
        }
        counts["downloaded"] += 1

    _write_json(
        AUTO_ARTICLES_PATH,
        {
            "retrieved_at_utc": retrieved_at,
            "discovery_start": start.isoformat(),
            "discovery_end": end.isoformat(),
            "scan_status": "complete",
            "articles": articles,
        },
    )
    return counts

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

    Every uncached source URL must download successfully; retrieval errors propagate.
    """

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    previous: dict[str, dict] = {}
    if MANIFEST_PATH.is_file():
        manifest_payload = _read_json(MANIFEST_PATH)
        previous = manifest_payload.get("sources")
        if not isinstance(previous, dict):
            raise ValueError("WAM source manifest must contain a sources object")

    manifest: dict[str, dict] = {}
    counts = {"total": 0, "downloaded": 0, "reused": 0}
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for url in _source_urls():
        counts["total"] += 1
        archive_path = ARCHIVE_DIR / _archive_name(url)
        old = previous.get(url, {})
        if not force and archive_path.is_file() and old.get("status") == 200:
            manifest[url] = {**old, "archive_path": str(archive_path.relative_to(RAW_DIR))}
            counts["reused"] += 1
            continue
        status, content_type, body = _fetch(url)
        if status != 200:
            raise RuntimeError(f"WAM source returned HTTP {status}: {url}")
        entry = {
            "url": url,
            "retrieved_at_utc": retrieved_at,
            "status": status,
            "content_type": content_type,
            "archive_path": str(archive_path.relative_to(RAW_DIR)) if body else None,
            "sha256": hashlib.sha256(body).hexdigest() if body else None,
            "error": None,
        }
        archive_path.write_bytes(body)
        counts["downloaded"] += 1
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
