"""Google Trends employment search indicators: fetch, load, and export.

The normal update path queries the UAE monthly timeline from Google Trends.
An online failure is reported directly; the raw JSON cache is used only when
an operator explicitly requests ``--skip-download``.
"""

from __future__ import annotations

import csv
import json
import math
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from .paths import DATA_DIR


from .db import (  # noqa: E402
    connect,
    replace,
)

RAW_EMPLOYMENT = DATA_DIR / "raw" / "employment"
EXPORT_PATH = DATA_DIR / "工作搜索热度.csv"
GOOGLE_TRENDS_CACHE = RAW_EMPLOYMENT / "google_trends_uae_monthly.json"
GOOGLE_TRENDS_EXPLORE_URL = "https://trends.google.com/trends/api/explore"
GOOGLE_TRENDS_MULTILINE_URL = (
    "https://trends.google.com/trends/api/widgetdata/multiline"
)

# HTFA 监测政府金融搜索指数模块期望的列
KEYWORDS = ("work in dubai", "work in uae")
SEARCH_TABLE = "employment_search_index"

_GOOGLE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://trends.google.com/trends/explore?geo=AE",
}


@contextmanager
def _transaction(con):
    """显式事务上下文（BEGIN/COMMIT/ROLLBACK）。

    注意：duckdb 1.5.5 的 con.begin() 上下文管理器在退出时会关闭连接，
    与 update_data.py 在同一连接上继续 log_run 的约定冲突，因此自行管理事务。
    """

    con.execute("BEGIN TRANSACTION")
    try:
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


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


def _google_request_json(url: str, *, params: dict[str, str]) -> dict:
    response = requests.get(
        url, params=params, headers=_GOOGLE_HEADERS, timeout=(15, 90)
    )
    response.raise_for_status()
    return _decode_google_json(response.text)


def _fetch_google_trends() -> tuple[list[dict[str, object]], str]:
    """从 Google Trends Explore 图表请求阿联酋两组词的完整时间线。"""

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
    payload = cache.get("response", cache)
    if not isinstance(payload, dict):
        raise ValueError("Google Trends 缓存的 response 结构无效")
    rows = _rows_from_timeline(payload)
    fetched_at = str(cache.get("fetched_at_utc") or "抓取时间未知")
    month_count = len({row["month"] for row in rows})
    return rows, f"Google Trends 缓存 {month_count} 个月（{fetched_at}）"


def export_wide(rows: list[dict[str, object]], target: Path) -> int:
    """从 long 行导出宽表 CSV（Time, 'work in dubai', 'work in uae'）。

    月份升序；整数值不带小数位（与原始 CSV 观感一致）。
    """

    by_month: dict[str, dict[str, object]] = {}
    for row in rows:
        key = row["month"].strftime("%Y-%m-%d") if hasattr(row["month"], "strftime") else str(row["month"])
        by_month.setdefault(key, {})[row["keyword"]] = row["value"]

    def fmt(value: object) -> str:
        if value is None:
            return ""
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)

    with open(target, "w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["Time", *KEYWORDS])
        for key in sorted(by_month):
            writer.writerow([key, fmt(by_month[key].get("work in dubai")), fmt(by_month[key].get("work in uae"))])
    return len(by_month)


def update(
    con, *, force: bool = False, skip_download: bool = False
) -> dict[str, object]:
    """在线刷新 Google Trends；仅在显式离线模式下读取原始 JSON 缓存。"""

    if skip_download:
        rows, note = _cached_google_trends()
    else:
        rows, note = _fetch_google_trends()

    with _transaction(con):
        replace(con, SEARCH_TABLE, rows)
    return {
        "status": "ok",
        "rows": len(rows),
        "note": f"{note}；{len(rows)} 个 (月, 关键词) 观测已入库",
    }


def merge(workbook_path: Path) -> dict[str, object]:
    """从库导出宽表 CSV 到 data/UAE/工作搜索热度.csv（监测模块的输入文件）。

    本模块无目标 sheet；workbook_path 参数保留以符合 merge 统一签名，实际不使用。
    """

    con = connect(read_only=True)
    try:
        rows = [
            {"month": month, "keyword": keyword, "value": value}
            for month, keyword, value in con.execute(
                f"SELECT month, keyword, value FROM {SEARCH_TABLE} ORDER BY month"
            ).fetchall()
        ]
    finally:
        con.close()
    month_count = export_wide(rows, EXPORT_PATH)
    return {
        "status": "ok",
        "note": f"已导出 {EXPORT_PATH.name}：{month_count} 个月 × {len(KEYWORDS)} 个关键词",
    }


if __name__ == "__main__":
    # 自检提示（不执行网络/工作簿写入）
    print("[source_employment] 运行 data\\update_data.py --source employment 入库；"
          "data\\merge_workbook.py --source employment 导出 CSV。")
