"""Discover and parse official UAE business licence announcements."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)
MEDIA_OFFICE = "https://mediaoffice.ae"
NEWS_LISTING_PAGE = f"{MEDIA_OFFICE}/en/economy"
NEWS_LIST_API = f"{MEDIA_OFFICE}/api/feature/news/list"
NEWS_PAGE_SIZE = 100
NEWS_MAX_PAGES = 300
NEWS_REQUEST_DELAY_SECONDS = 0.12

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

PATTERNS = [
    re.compile(
        r"issued?\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"in\s+([A-Z][a-z]+)\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"issues?\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"in\s+([A-Z][a-z]+)\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"(?:were\s+)?issued\s+in\s+([A-Z][a-z]+)\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"([\d,]+)\s+new\s+licen[cs]es?\s+in\s+([A-Z][a-z]+)\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"issued?\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"in\s+((?:H[12]|Q[1-4]))\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"in\s+((?:H[12]|Q[1-4]))\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"([\d,]+)\s+new\s+business\s+licen[cs]es?\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"issued?\s+([\d,]+)\s+new\s+licen[cs]es?\s+(\d{4})",
        re.I,
    ),
    re.compile(
        r"(?:issued?|issues?)\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"(?:during|in)\s+(?:the\s+)?first\s+"
        r"(3|three|6|six|9|nine|10|ten|11|eleven)\s+months?\s+"
        r"(?:of\s+)?(\d{4})",
        re.I,
    ),
    re.compile(
        r"([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"(?:during|in)\s+(?:the\s+)?first\s+"
        r"(3|three|6|six|9|nine|10|ten|11|eleven)\s+months?\s+"
        r"(?:of\s+)?(\d{4})",
        re.I,
    ),
    re.compile(
        r"(?:issued?|issues?)\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"(?:during|in)\s+(?:the\s+)?(first|second)\s+half\s+(?:of\s+)?(\d{4})",
        re.I,
    ),
    re.compile(
        r"([\d,]+)\s+new\s+business\s+licen[cs]es?\s+"
        r"(?:during|in)\s+(?:the\s+)?(first|second)\s+half\s+(?:of\s+)?(\d{4})",
        re.I,
    ),
]


class _ListingInputs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "input":
            return
        fields = dict(attrs)
        identifier = fields.get("id")
        value = fields.get("value")
        if identifier and value is not None:
            self.values[identifier] = value


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)



def _fetch_listing_inputs() -> dict[str, str]:
    request = urllib.request.Request(NEWS_LISTING_PAGE, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        source = response.read().decode("utf-8")
    parser = _ListingInputs()
    parser.feed(source)
    required = ("NewsWidgetSource", "hdnculture", "hdnCategory", "hdnSubCategory")
    missing = [field for field in required if not parser.values.get(field)]
    if missing:
        raise ValueError(f"Media Office economy page is missing fields: {missing}")
    return parser.values


def _fetch_news_page(fields: dict[str, str], page_number: int) -> dict:
    body = {
        "sourceID": fields["NewsWidgetSource"],
        "pageNo": page_number,
        "pageSize": NEWS_PAGE_SIZE,
        "culture": fields["hdnculture"],
        "itemID": fields["hdnCategory"],
        "SubCategory": fields["hdnSubCategory"],
        "newsDate": "",
        "newsKeyword": "",
    }
    request = urllib.request.Request(
        NEWS_LIST_API,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        envelope = json.loads(response.read().decode("utf-8"))
    if not isinstance(envelope, str):
        raise ValueError("Media Office news API response envelope must be a JSON string")
    payload = json.loads(envelope)
    if not isinstance(payload, dict):
        raise ValueError("Media Office news API response must contain an object")
    return payload


def _published_date(item: dict) -> date:
    value = item.get("Date")
    if value:
        try:
            return datetime.strptime(value, "%A, %B %d, %Y").date()
        except ValueError as exc:
            raise ValueError(f"Invalid Media Office publication date: {value!r}") from exc

    link = item.get("DetailPageLink")
    if not isinstance(link, str) or not link:
        raise ValueError("Media Office news item is missing DetailPageLink")
    path = urlsplit(link).path
    match = re.search(
        r"/news/(20\d{2})/([a-z]+)/([0-3]\d)-([01]\d)/",
        path,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Media Office news URL has no publication date: {link!r}")
    year, month_name, day, month = match.groups()
    expected_month = MONTHS.get(month_name.casefold())
    if expected_month != int(month):
        raise ValueError(f"Media Office news URL has an invalid month: {link!r}")
    try:
        return date(int(year), int(month), int(day))
    except ValueError as exc:
        raise ValueError(f"Media Office news URL has an invalid date: {link!r}") from exc


def _period_month(period: str, year: str) -> tuple[str, str]:
    normalized = period.casefold()
    if normalized in MONTHS:
        month, kind = MONTHS[normalized], "month"
    elif normalized.startswith("q") and normalized[1:].isdigit():
        quarter = int(normalized[1:])
        if quarter not in {1, 2, 3, 4}:
            raise ValueError(f"Invalid quarter in Media Office article: {period!r}")
        month, kind = quarter * 3, "quarter"
    elif normalized in {"h1", "first"}:
        month, kind = 6, "half_year"
    elif normalized in {"h2", "second"}:
        month, kind = 12, "half_year"
    elif normalized in {"3", "three", "6", "six", "9", "nine", "10", "ten", "11", "eleven"}:
        month = {"3": 3, "three": 3, "6": 6, "six": 6, "9": 9, "nine": 9,
                 "10": 10, "ten": 10, "11": 11, "eleven": 11}[normalized]
        kind = "year_to_date"
    elif normalized == "full_year":
        month, kind = 12, "year"
    else:
        raise ValueError(f"Unsupported Media Office reporting period: {period!r}")
    return f"{int(year):04d}-{month:02d}", kind


def extract_from_text(
    text: str,
    *,
    source_url: str,
    published_at: date,
    headline: str,
) -> list[dict]:
    observations: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for pattern in PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            value = int(groups[0].replace(",", ""))
            if len(groups) == 2:
                period, year = "full_year", groups[1]
            else:
                period, year = groups[1], groups[2]
            month, period_kind = _period_month(period, year)
            key = (month, value, period_kind)
            if key in seen:
                continue
            seen.add(key)
            observations.append(
                {
                    "month": month,
                    "value": value,
                    "period": period,
                    "year": year,
                    "period_kind": period_kind,
                    "note": f"Media Office announcement: {period} {year}, {value:,} licences",
                    "snippet": text[max(0, match.start() - 80): match.end() + 80][:200],
                    "source_url": source_url,
                    "published_at": published_at,
                    "headline": headline,
                }
            )
    return observations


def discover_official_news(*, start: date) -> dict:
    """Scan the official economy listing back to ``start`` and extract values."""

    if not isinstance(start, date):
        raise TypeError("start must be a datetime.date")
    fields = _fetch_listing_inputs()
    first_page = _fetch_news_page(fields, 1)
    try:
        page_count = int(first_page["PageCount"])
        total_records = int(first_page["TotalRecordCount"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Media Office news API pagination metadata is invalid") from exc
    if page_count < 1 or total_records < 1:
        raise RuntimeError("Media Office economy listing returned no news items")
    if page_count > NEWS_MAX_PAGES:
        raise RuntimeError(
            f"Media Office news listing exceeds the scan limit: {page_count} pages"
        )

    observations: list[dict] = []
    previous_date: date | None = None
    scanned_through: date | None = None
    pages_scanned = 0
    for page_number in range(1, page_count + 1):
        if page_number == 1:
            payload = first_page
        else:
            time.sleep(NEWS_REQUEST_DELAY_SECONDS)
            payload = _fetch_news_page(fields, page_number)
        if payload.get("PageNo") != page_number or payload.get("PageCount") != page_count:
            raise ValueError("Media Office news pagination changed during the scan")
        items = payload.get("Items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"Media Office news page {page_number} has no items")
        pages_scanned += 1
        reached_start = False
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"Media Office news page {page_number} has an invalid item")
            published_at = _published_date(item)
            if previous_date is not None and published_at > previous_date:
                raise ValueError("Media Office news API is not ordered newest first")
            previous_date = published_at
            scanned_through = scanned_through or published_at
            if published_at < start:
                reached_start = True
                break
            headline = item.get("NewsTitle")
            link = item.get("DetailPageLink")
            body = item.get("FullText")
            if not isinstance(headline, str) or not headline.strip():
                raise ValueError("Media Office news item is missing NewsTitle")
            if not isinstance(link, str) or not link:
                raise ValueError("Media Office news item is missing DetailPageLink")
            if not isinstance(body, str) or not body.strip():
                raise ValueError(f"Media Office news item has no article text: {link}")
            source_url = urljoin(MEDIA_OFFICE, link)
            if urlsplit(source_url).netloc.casefold() != "mediaoffice.ae":
                raise ValueError(f"Media Office news item has an external URL: {link!r}")
            observations.extend(
                extract_from_text(
                    fetch_text_from_html(body),
                    source_url=source_url,
                    published_at=published_at,
                    headline=headline,
                )
            )
        if reached_start:
            break

    if scanned_through is None:
        raise RuntimeError("Media Office news scan did not inspect any dated item")
    return {
        "pages": pages_scanned,
        "observations": observations,
        "scanned_through": scanned_through,
    }


def fetch_text_from_html(source: str) -> str:
    parser = _TextExtractor()
    parser.feed(source)
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()
