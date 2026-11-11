"""Google Trends employment search indicators: fetch, load, and workbook merge.

The normal update path queries the UAE monthly timeline from Google Trends.
An online failure is reported directly; the raw JSON cache is used only when
an operator explicitly requests ``--skip-download``.
"""

from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from curl_cffi import requests

from .db import transaction
from .db import replace
from .paths import DATA_DIR
from .workbook_sheet_writer import merge_source_sheet, pivot_indicator_rows

TARGET_SHEET = "月度_工作搜索热度"
RAW_EMPLOYMENT = DATA_DIR / "raw" / "employment"
GOOGLE_TRENDS_CACHE = RAW_EMPLOYMENT / "google_trends_uae_monthly.json"
GOOGLE_TRENDS_EXPLORE_URL = "https://trends.google.com/trends/api/explore"
GOOGLE_TRENDS_MULTILINE_URL = (
    "https://trends.google.com/trends/api/widgetdata/multiline"
)

# HTFA 监测政府金融搜索指数模块期望的列
KEYWORDS = ("work in dubai", "work in uae")
SEARCH_TABLE = "employment_search_index"

_GOOGLE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://trends.google.com/trends/explore?geo=AE",
}


def _decode_google_json(response_text: str) -> dict:
    """移除 Google Trends 响应的 XSSI 前缀并解析 JSON。"""

    text = response_text.lstrip()
    if text.startswith(")]}'"):
        if text.startswith(")]}',"):
            text = text[5:].lstrip("\r\n")
        else:
            _, separator, text = text.partition("\n")
            if not separator:
                raise ValueError("Google Trends 返回了不完整的 JSON 响应")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Google Trends 返回了非对象 JSON")
    return payload


def _rows_from_timeline(payload: dict) -> list[dict[str, object]]:
    """将 Google Trends 时间线转成月度 long 行；排除未完成的当月。"""

    default_payload = payload.get("default") or {}
    if not isinstance(default_payload, dict):
        raise ValueError("Google Trends 响应的 default 结构无效")
    timeline = default_payload.get("timelineData") or []
    if not isinstance(timeline, list) or not timeline:
        raise ValueError("Google Trends 响应没有 timelineData")

    # Google 的时间戳以 UTC 表示；以阿联酋本地日期排除当前未完成月份。
    uae_today = (datetime.now(timezone.utc) + timedelta(hours=4)).date()
    current_month = date(uae_today.year, uae_today.month, 1)
    grouped: dict[date, dict[str, list[float]]] = {}
    for point in timeline:
        if not isinstance(point, dict):
            raise ValueError("Google Trends 时间点结构无效")
        if str(point.get("isPartial", "")).casefold() == "true":
            continue
        try:
            timestamp = int(point["time"])
            period = datetime.fromtimestamp(timestamp, timezone.utc).date()
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise ValueError(f"Google Trends 时间点无效: {point!r}") from exc
        month = date(period.year, period.month, 1)
        if month >= current_month:
            continue
        values = point.get("value") or []
        if not isinstance(values, list) or len(values) != len(KEYWORDS):
            raise ValueError(
                f"Google Trends 时间点应有 {len(KEYWORDS)} 个关键词值，实际 {len(values)}"
            )
        month_values = grouped.setdefault(month, {keyword: [] for keyword in KEYWORDS})
        for keyword, raw_value in zip(KEYWORDS, values):
            if raw_value is None or str(raw_value).strip() == "":
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Google Trends {keyword} 数值无效: {raw_value!r}"
                ) from exc
            if math.isfinite(value):
                month_values[keyword].append(value)

    rows: list[dict[str, object]] = []
    for month, keyword_values in sorted(grouped.items()):
        for keyword in KEYWORDS:
            values = keyword_values[keyword]
            if values:
                rows.append(
                    {
                        "month": month,
                        "keyword": keyword,
                        "value": sum(values) / len(values),
                    }
                )
    if not rows:
        raise ValueError("Google Trends 响应中没有可用的完整月份")
    if {row["keyword"] for row in rows} != set(KEYWORDS):
        raise ValueError("Google Trends 响应未覆盖全部关键词")
    return rows


def _google_request_json(
    url: str, *, params: dict[str, str], session: requests.Session
) -> dict:
    for attempt in range(3):
        response = session.get(url, params=params, timeout=(15, 90))
        if response.status_code != 429 or attempt == 2:
            response.raise_for_status()
            return _decode_google_json(response.text)
        retry_after = response.headers.get("Retry-After", "")
        delay = float(retry_after) if retry_after.isdigit() else 10 * (attempt + 1)
        if delay > 60:
            response.raise_for_status()
        time.sleep(delay)
    raise RuntimeError("Google Trends retry loop ended unexpectedly")


def _fetch_google_trends() -> tuple[list[dict[str, object]], str]:
    """从 Google Trends Explore 图表请求阿联酋两组词的完整时间线。"""

    with requests.Session(impersonate="chrome", headers=_GOOGLE_HEADERS) as session:
        # Establish Google's public session cookies before requesting widget tokens.
        # The landing page and API have separate rate limits; API status is decisive.
        session.get("https://trends.google.com/trends/explore?geo=AE", timeout=(15, 90))
        return _fetch_google_timeline(session)


def _fetch_google_timeline(session: requests.Session) -> tuple[list[dict[str, object]], str]:
    request = {
        "comparisonItem": [
            {"keyword": keyword, "geo": "AE", "time": "all"}
            for keyword in KEYWORDS
        ],
        "category": 0,
        "property": "",
    }
    explore = _google_request_json(
        GOOGLE_TRENDS_EXPLORE_URL,
        session=session,
        params={
            "hl": "en-US",
            "tz": "0",
            "req": json.dumps(request, separators=(",", ":")),
        },
    )
    widgets = explore.get("widgets") or []
    widget = next(
        (item for item in widgets if item.get("id") == "TIMESERIES"), None
    )
    if not widget or not widget.get("token") or not widget.get("request"):
        raise ValueError("Google Trends Explore 响应缺少 TIMESERIES 查询信息")

    payload = _google_request_json(
        GOOGLE_TRENDS_MULTILINE_URL,
        session=session,
        params={
            "hl": "en-US",
            "tz": "0",
            "req": json.dumps(widget["request"], separators=(",", ":")),
            "token": str(widget["token"]),
        },
    )
    rows = _rows_from_timeline(payload)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cache = {
        "fetched_at_utc": fetched_at,
        "geo": "AE",
        "keywords": list(KEYWORDS),
        "response": payload,
    }
    GOOGLE_TRENDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = GOOGLE_TRENDS_CACHE.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(GOOGLE_TRENDS_CACHE)
    month_count = len({row["month"] for row in rows})
    return rows, f"Google Trends 在线抓取 {month_count} 个月（{fetched_at}）"


def _cached_google_trends() -> tuple[list[dict[str, object]], str]:
    """读取最近一次成功抓取的 Google Trends 原始响应。"""

    if not GOOGLE_TRENDS_CACHE.is_file():
        raise FileNotFoundError(f"Google Trends 缓存不存在: {GOOGLE_TRENDS_CACHE}")
    cache = json.loads(GOOGLE_TRENDS_CACHE.read_text(encoding="utf-8"))
    if not isinstance(cache, dict):
        raise ValueError("Google Trends 缓存结构无效")
    if cache.get("geo") != "AE" or cache.get("keywords") != list(KEYWORDS):
        raise ValueError("Google Trends 缓存的地区或关键词与当前指标不一致")
    payload = cache.get("response")
    if not isinstance(payload, dict):
        raise ValueError("Google Trends 缓存的 response 结构无效")
    rows = _rows_from_timeline(payload)
    fetched_at = cache.get("fetched_at_utc")
    if not isinstance(fetched_at, str) or not fetched_at:
        raise ValueError("Google Trends 缓存缺少抓取时间")
    month_count = len({row["month"] for row in rows})
    return rows, f"Google Trends 缓存 {month_count} 个月（{fetched_at}）"


def update(
    con, *, force: bool = False, skip_download: bool = False
) -> dict[str, object]:
    """在线刷新 Google Trends；仅在显式离线模式下读取原始 JSON 缓存。"""

    if skip_download:
        rows, note = _cached_google_trends()
    else:
        rows, note = _fetch_google_trends()

    with transaction(con):
        replace(con, SEARCH_TABLE, rows)
    return {
        "status": "ok",
        "rows": len(rows),
        "note": f"{note}；{len(rows)} 个 (月, 关键词) 观测已入库",
    }


def _sheet_spec(con) -> dict[str, Any]:
    names = {
        "work in dubai": "阿联酋:Google搜索热度(work in dubai)",
        "work in uae": "阿联酋:Google搜索热度(work in uae)",
    }
    rows = pivot_indicator_rows(
        con.execute(
            f"SELECT month, keyword, value FROM {SEARCH_TABLE}"
        ).fetchall(),
        lambda keyword: names[keyword],
    )
    return {
        "name": TARGET_SHEET,
        "title": "Google Trends 阿联酋工作搜索热度",
        "indicators": list(names.values()),
        "rows": rows,
    }


def merge(workbook_path: Path) -> dict:
    """Rebuild this source's workbook sheet from DuckDB."""
    return merge_source_sheet(workbook_path, _sheet_spec)
