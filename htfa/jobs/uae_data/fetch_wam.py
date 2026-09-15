"""Fetch and archive WAM source material used by the war-statistics pipeline.

The WAM site exposes an official monthly news sitemap.  Its article pages are
rendered by Angular for normal HTTP clients, but the rendered page contains a
standard ``NewsArticle`` JSON-LD block.  This module discovers relevant UAE
air-defence articles from the sitemap, renders them with the locally installed
Chrome browser, and stores the extracted JSON-LD as an auditable raw cache.

Numerical interpretation is intentionally kept in :mod:`source_wam`; this
module only discovers, downloads, renders, and archives source material.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
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
AUTO_RENDER_TIMEOUT_SECONDS = 90
AUTO_VIRTUAL_TIME_BUDGET_MS = 10000

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


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
        raise ValueError(f"WAM daily registry is empty: {DAILY_PATH}")
    return max(dates)


def _is_auto_candidate(title: str, url: str) -> bool:
    text = f"{title} {url}".casefold()
    return any(term in text for term in _AUTO_TITLE_TERMS) and any(
        term in text for term in _AUTO_WEAPON_TERMS
    )


def _sitemap_month_urls(start: date, end: date) -> list[str]:
    status, _, body, error = _fetch(SITEMAP_INDEX_URL)
    if body is None or status != 200:
        raise RuntimeError(f"WAM sitemap index failed: {error or status}")
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

    end = end or datetime.now(timezone.utc).date()
    start = start or (_latest_registry_date() - timedelta(days=AUTO_LOOKBACK_DAYS))
    articles: dict[str, dict] = {}
    for sitemap_url in _sitemap_month_urls(start, end):
        status, _, body, error = _fetch(sitemap_url)
        if body is None or status != 200:
            raise RuntimeError(f"WAM monthly sitemap failed: {sitemap_url}: {error or status}")
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
            if not url or not published or not _is_auto_candidate(title, url):
                continue
            try:
                published_date = date.fromisoformat(published[:10])
            except ValueError:
                continue
            if not (start <= published_date <= end):
                continue
            articles[url] = {
                "url": url,
                "sitemap_title": title,
                "sitemap_published_at": published,
            }
    return sorted(articles.values(), key=lambda item: (item["sitemap_published_at"], item["url"]))


def _chrome_path() -> str | None:
    configured = os.environ.get("WAM_CHROME_PATH", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return str(candidate)
    return shutil.which("chrome") or shutil.which("msedge")


def _render_article(url: str) -> tuple[str | None, str | None]:
    """Render one article and return the resulting DOM or an error."""

    chrome = _chrome_path()
    if not chrome:
        return None, "Chrome/Edge not found; set WAM_CHROME_PATH to a browser executable"
    with tempfile.TemporaryDirectory(prefix="wam-chrome-") as profile:
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--user-data-dir={profile}",
            f"--virtual-time-budget={AUTO_VIRTUAL_TIME_BUDGET_MS}",
            "--dump-dom",
            url,
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=AUTO_RENDER_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"browser render failed: {exc}"
    rendered = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0 or not rendered.strip():
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        return None, f"browser render exit={completed.returncode}: {detail[:500]}"
    return rendered, None


def _extract_news_article(dom: str) -> dict | None:
    pattern = re.compile(
        r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    for raw in pattern.findall(dom):
        try:
            payload = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
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


def _load_auto_payload() -> dict:
    payload = _read_json(AUTO_ARTICLES_PATH)
    payload.setdefault("articles", {})
    if not isinstance(payload["articles"], dict):
        payload["articles"] = {}
    return payload


def load_auto_articles() -> list[dict]:
    """Read successfully rendered article records for offline reprocessing."""

    payload = _load_auto_payload()
    return [
        value
        for value in payload["articles"].values()
        if isinstance(value, dict) and value.get("status") == "ok"
    ]


def refresh_auto_articles(*, force: bool = False) -> dict[str, int]:
    """Discover and render new WAM articles, retaining an auditable cache."""

    end = datetime.now(timezone.utc).date()
    start = _latest_registry_date() - timedelta(days=AUTO_LOOKBACK_DAYS)
    discovered = discover_auto_articles(start=start, end=end)
    payload = _load_auto_payload()
    articles = payload["articles"]
    counts = {"discovered": len(discovered), "downloaded": 0, "reused": 0, "failed": 0}
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for item in discovered:
        url = item["url"]
        old = articles.get(url, {})
        reusable = (
            not force
            and old.get("status") == "ok"
            and old.get("sitemap_published_at") == item["sitemap_published_at"]
            and old.get("article_body")
        )
        if reusable:
            articles[url] = {**old, **item}
            counts["reused"] += 1
            continue
        dom, error = _render_article(url)
        record = {**item, "retrieved_at_utc": retrieved_at}
        if error:
            record.update({"status": "failed", "error": error})
            counts["failed"] += 1
        else:
            article = _extract_news_article(dom or "")
            if not article or not article.get("articleBody"):
                record.update({"status": "failed", "error": "NewsArticle JSON-LD/articleBody not found"})
                counts["failed"] += 1
            else:
                record.update(
                    {
                        "status": "ok",
                        "headline": article.get("headline") or item["sitemap_title"],
                        "description": article.get("description"),
                        "article_body": article["articleBody"],
                        "date_published": article.get("datePublished"),
                        "date_modified": article.get("dateModified"),
                        "archive_path": _archive_auto_dom(url, dom or ""),
                        "error": None,
                    }
                )
                counts["downloaded"] += 1
        articles[url] = record

    _write_json(
        AUTO_ARTICLES_PATH,
        {
            "retrieved_at_utc": retrieved_at,
            "discovery_start": start.isoformat(),
            "discovery_end": end.isoformat(),
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
