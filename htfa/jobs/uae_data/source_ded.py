"""Data Dubai DED 企业注册数据源：自动下载、月度聚合并写入 DuckDB。

官方新执照公告由媒体办公室新闻 API 扫描并写入 DuckDB 候选表；``merge()``
从 ``ded_monthly`` / ``ded_monthly_by_type`` 重建 ``月度_DED`` 工作表。

统计口径：
- records      ：快照记录行数（按发照日期归月）；
- enterprises  ：当月有发证活动的企业数（commerce_number 按发照月去重，剔除占位
                  '0'/空；快照中企业号↔发照月份一一对应，故企业号首现筛重数值
                  即当月有发证活动的企业数，正名不改数）；
- licences     ：当月新发执照数（main_license_number 按发照月去重，同号剔除）；
- official     ：官方公布数字（由官方新闻候选表生成）；
- 单期存量快照无法给出流量，历史月份低估、近期可信。
"""

from __future__ import annotations

import bz2
import calendar
import csv
import gzip
import hashlib
import http.cookiejar
import io
import json
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


from .paths import DATA_DIR


from .db import (  # noqa: E402
    connect,
    replace,
)
from . import fetch_official_news  # noqa: E402
from .workbook_sheet_writer import read_indicator_metadata, write_indicator_sheets

DATA_DUBAI = "https://data.dubai"
DATASET_PAGE = (
    "https://data.dubai/en/l/460521?com_dda_data_and_statistics_ThemeId=36962"
)
DATASET_ID = "460521"
DOWNLOAD_API = f"{DATA_DUBAI}/o/dda/data-services/dataset-download"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)
CHUNK_SIZE = 1024 * 1024
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# 输入与审计输出固定在 data/UAE/raw/ded/DED_data，不跟随 cwd
RAW_DED = DATA_DIR / "raw" / "ded"
OUT = RAW_DED / "DED_data"
RAW = OUT / "raw"
BACKUP_DIR = RAW_DED / "backups"

SHEET_NAME = "月度_DED"

MONTHLY_TABLE = "ded_monthly"
BY_TYPE_TABLE = "ded_monthly_by_type"
OFFICIAL_NEWS_TABLE = "ded_official_news_candidates"
OFFICIAL_NEWS_STATE_TABLE = "ded_official_news_scan_state"


class AuthRequiredError(RuntimeError):
    """资源需要登录（UAE Pass / Dubai ID），携带会话后重试。"""


class IncompleteDownloadError(RuntimeError):
    """下载字节数与 Content-Length 不符（连接被截断），需要重试。"""


# --------------------------------------------------------------------------
# 下载基础设施（与 fetch_ded_license.py 一致）
# --------------------------------------------------------------------------

def format_bytes(size):
    size = int(size or 0)
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return "0 B"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while True:
            block = source.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def build_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler(),
    )


def make_request(url, headers=None):
    if isinstance(url, urllib.request.Request):
        return url
    headers = dict(headers or {})
    headers.setdefault("User-Agent", UA)
    return urllib.request.Request(url, headers=headers)


def raise_if_sso_url(response):
    """最终 URL 被 SSO 拦截时抛出 AuthRequiredError。"""
    final = getattr(response, "url", "") or response.geturl()
    if "smartsso.dubai.gov.ae" in final or "/isam/sps/" in final:
        raise AuthRequiredError(
            "请求被重定向到迪拜政府统一登录（smartsso.dubai.gov.ae，需要登录）。"
            "自动更新已终止，不会将登录页面当作数据。"
        )
    return response


def raise_if_sso_page(text):
    """HTML 内容为 SSO 登录页时抛出 AuthRequiredError。"""
    if "smartsso.dubai.gov.ae" in text or "/isam/sps/" in text:
        raise AuthRequiredError(
            "返回的是登录页（smartsso.dubai.gov.ae），该资源需要登录。"
            "详见 README.md 的认证说明。"
        )


def read_text(opener, url, headers=None, timeout=90, retries=4):
    req = make_request(url, headers)
    last = None
    for attempt in range(retries + 1):
        try:
            with opener.open(req, timeout=timeout) as response:
                raise_if_sso_url(response)
                text = response.read().decode("utf-8")
                raise_if_sso_page(text)
                return text
        except AuthRequiredError:
            raise
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in RETRYABLE_STATUS and attempt < retries:
                time.sleep(max(int(exc.headers.get("Retry-After", 0) or 0), 2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last


def stream_to_file(opener, url, dest, headers=None, timeout=180, retries=4):
    """流式下载到 dest，返回 (最终响应 URL, Content-Type)。"""
    req = make_request(url, headers)
    last = None
    for attempt in range(retries + 1):
        try:
            with opener.open(req, timeout=timeout) as response:
                raise_if_sso_url(response)
                final_url = response.geturl()
                ctype = response.headers.get("Content-Type", "")
                expected = int(response.headers.get("Content-Length") or 0)
                total = 0
                last_report = time.time()
                head = response.read(CHUNK_SIZE)
                if b"smartsso.dubai.gov.ae" in head or b"/isam/sps/" in head:
                    raise AuthRequiredError(
                        "返回的是登录页（smartsso.dubai.gov.ae），该资源需要登录。"
                        "详见 README.md 的认证说明。"
                    )
                with open(dest, "wb") as target:
                    if head:
                        target.write(head)
                        total += len(head)
                    while True:
                        block = response.read(CHUNK_SIZE)
                        if not block:
                            break
                        target.write(block)
                        total += len(block)
                        now = time.time()
                        if now - last_report >= 10:  # 每 10 秒报一次进度
                            print(f"  ... {format_bytes(total)}", flush=True)
                            last_report = now
                if expected and total != expected:
                    raise IncompleteDownloadError(
                        f"下载不完整: 期望 {expected} 字节，实际 {total} 字节"
                    )
                return final_url, ctype
        except IncompleteDownloadError as exc:
            last = exc
            print(f"  ! {exc}，重试 ({attempt + 1}/{retries + 1})", flush=True)
            dest.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
        except AuthRequiredError:
            dest.unlink(missing_ok=True)
            raise
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in RETRYABLE_STATUS and attempt < retries:
                time.sleep(max(int(exc.headers.get("Retry-After", 0) or 0), 2 ** attempt))
                continue
            dest.unlink(missing_ok=True)
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            dest.unlink(missing_ok=True)
            raise
    raise last


def fetch_data_dubai_files(opener, dataset_id, headers=None, prefer="csv"):
    """通过官方 dataset-download 接口获取全部快照文件（签名直链）。

    返回 [{"file_name":..., "file_extension":..., "file_size":..., "file_url":...}]
    """
    page_url = (
        f"{DATA_DUBAI}/en/l/{dataset_id}"
        "?com_dda_data_and_statistics_ThemeId=36962"
    )
    print(f"抓取数据集页面: {page_url}")
    html_text = read_text(opener, page_url, headers, timeout=60, retries=2)
    token_match = re.search(r"Liferay\.authToken\s*=\s*'([^']+)'", html_text)
    if not token_match:
        raise RuntimeError("Data Dubai 页面未提供 CSRF token")

    files = []
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "datasetId": dataset_id,
            "page": str(page),
            "pageSize": "100",
            "sortDir": "desc",
        })
        api_req = urllib.request.Request(
            f"{DOWNLOAD_API}?{query}",
            headers={
                "User-Agent": UA,
                "Accept": "application/json",
                "X-CSRF-Token": token_match.group(1),
                "Referer": page_url,
            },
        )
        payload = json.loads(read_text(opener, api_req, headers={}, timeout=60, retries=2))
        if not payload.get("success"):
            raise RuntimeError(f"dataset-download 接口失败: {payload.get('message')}")
        data = payload.get("data") or {}
        for folder in data.get("metadata") or []:
            for item in folder.get("files") or []:
                name = str(item.get("file_name") or "")
                ext = str(item.get("file_extension") or "").lower()
                if prefer == "json":
                    pick = ext == "json"
                else:
                    pick = ext == "csv"
                if pick and item.get("file_url"):
                    files.append({
                        "file_name": name,
                        "file_extension": ext,
                        "file_size": int(item.get("file_size") or 0),
                        "file_url": item["file_url"],
                    })
        pagination = data.get("pagination") or {}
        page_count = int(pagination.get("page_count") or 1)
        if page >= page_count:
            break
        page += 1
    if not files:
        raise RuntimeError(f"数据集 {dataset_id} 没有可用的 CSV/JSON 文件")
    return files


def detect_format(path):
    name = path.name.lower()
    if name.endswith(".gz") or name.endswith(".bz2"):
        name = name.rsplit(".", 1)[0]
    return "json" if name.endswith(".json") else "csv"


def open_text(path):
    """打开（必要时解压）UTF-8 文本流。"""
    raw = open(path, "rb")
    if path.name.lower().endswith(".gz"):
        raw = gzip.GzipFile(fileobj=raw)
    elif path.name.lower().endswith(".bz2"):
        raw = bz2.BZ2File(raw)
    return io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")


def sniff_delimiter(text):
    first = text.readline()
    text.seek(0)
    counts = {d: first.count(d) for d in ("\t", ";", "|", ",")}
    delim = max(counts, key=counts.get)
    return delim if counts[delim] > 0 else ","


def iter_rows(paths, limit=None):
    """按行产出 dict；paths 可为单文件或多文件列表（多分片）。"""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    produced = 0
    for path in paths:
        fmt = detect_format(path)
        if fmt == "csv":
            text = open_text(path)
            delim = sniff_delimiter(text)
            reader = csv.DictReader(text, delimiter=delim)
            for row in reader:
                if row and any(v is not None and v != "" for v in row.values()):
                    yield row
                    produced += 1
                    if limit and produced >= limit:
                        return
            text.close()
        else:
            size = path.stat().st_size
            text = open_text(path)
            if size < 500 * 1024 * 1024:
                try:
                    payload = json.load(text)
                except json.JSONDecodeError:
                    text.seek(0)
                    for line in text:
                        line = line.strip()
                        if not line:
                            continue
                        yield json.loads(line)
                        produced += 1
                        if limit and produced >= limit:
                            return
                    continue
                if isinstance(payload, dict):
                    for key in ("data", "records", "results", "items", "rows"):
                        if isinstance(payload.get(key), list):
                            payload = payload[key]
                            break
                    else:
                        payload = [payload]
                if not isinstance(payload, list):
                    raise ValueError(f"无法识别的 JSON 结构: {path.name}")
                for row in payload:
                    if isinstance(row, dict):
                        yield row
                        produced += 1
                        if limit and produced >= limit:
                            return
            else:
                for line in text:
                    line = line.strip()
                    if not line:
                        continue
                    yield json.loads(line)
                    produced += 1
                    if limit and produced >= limit:
                        return
            text.close()


DATE_PATTERNS = [
    re.compile(r"issue.*date", re.I),
    re.compile(r"licen[cs]e.*date", re.I),
    re.compile(r"date.*issu", re.I),
    re.compile(r"^issued", re.I),
    re.compile(r"registr.*date", re.I),
    re.compile(r"establishment.*date", re.I),
    re.compile(r"^created", re.I),
    re.compile(r"^date$", re.I),
    re.compile(r"date", re.I),
]
TYPE_PATTERNS = [
    re.compile(r"legal_type.*desc_en", re.I),
    re.compile(r"commerce_register_type.*desc_en", re.I),
    re.compile(r"licen[cs]e.*type", re.I),
    re.compile(r"^type", re.I),
    re.compile(r"^activit", re.I),
    re.compile(r"sector", re.I),
    re.compile(r"categor", re.I),
]


def guess_column(columns, patterns):
    normalized = {c: re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_") for c in columns}
    for pattern in patterns:
        for col in columns:
            if pattern.search(normalized[col]):
                return col
    return None


def parse_date(value):
    """解析常见日期格式，返回 (year, month) 或 None。"""
    if value is None:
        return None
    s = str(value).strip().strip('"')
    if not s:
        return None
    if s.isdigit():
        n = int(s)
        if n > 1e12:
            n /= 1000.0
        if 1e9 < n < 4.1e9:
            dt = datetime.fromtimestamp(n)
            return dt.year, dt.month
    date_part = re.split(r"[ T]", s.strip())[0][:10]
    if len(date_part) == 8 and date_part.isdigit():
        try:
            dt = datetime.strptime(date_part, "%Y%m%d")
            return dt.year, dt.month
        except ValueError:
            return None
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]
    if "/" in date_part:
        formats += ["%d/%m/%Y", "%m/%d/%Y"]
    elif "-" in date_part:
        formats += ["%d-%m-%Y"]
    elif "." in date_part:
        formats += ["%d.%m.%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_part, fmt)
            return dt.year, dt.month
        except ValueError:
            continue
    return None


def aggregate(rows, date_col, type_col, *, as_of=None):
    """月度聚合（与 fetch_ded_license.py 完全相同）。

    - monthly            ：记录行数（每条登记记录一张执照，按发照日期归月）
    - monthly_enterprise ：当月有发证活动的企业数——企业号(commerce_number)按
                           发照月去重（快照中企业号↔月份一一对应，首现筛重即活动数）
    - monthly_licence    ：当月新发执照数——执照号(main_license_number)按发照月去重
    """
    total = parsed = bad = 0
    monthly = Counter()
    ent_first = {}    # commerce_number -> 最早有效发照月份
    lic_first = {}    # main_license_number -> 最早有效发照月份
    by_type = Counter()
    date_min = date_max = None
    sample_rows = []
    reference = as_of or datetime.now().date()
    future_rows = []
    for row in rows:
        total += 1
        if len(sample_rows) < 3:
            sample_rows.append(row)
        month_key = None
        if date_col:
            result = parse_date(row.get(date_col))
            if result and 1900 <= result[0] <= 2100:  # 过滤占位/脏年份
                y, m = result
                if (y, m) > (reference.year, reference.month):
                    bad += 1
                    future_rows.append(dict(row))
                    continue
                parsed += 1
                month_key = f"{y:04d}-{m:02d}"
                monthly[month_key] += 1
                date_min = month_key if date_min is None else min(date_min, month_key)
                date_max = month_key if date_max is None else max(date_max, month_key)
                ent = str(row.get("commerce_number") or "").strip()
                if ent and ent != "0":
                    first = ent_first.get(ent)
                    if first is None or month_key < first:
                        ent_first[ent] = month_key
                lic = str(row.get("main_license_number") or "").strip()
                if lic:
                    first = lic_first.get(lic)
                    if first is None or month_key < first:
                        lic_first[lic] = month_key
            else:
                bad += 1
        if type_col:
            tval = str(row.get(type_col) or "").strip()
            by_type[(month_key or "unknown", tval or "(空)")] += 1
    monthly_enterprise = Counter(ent_first.values())
    monthly_licence = Counter(lic_first.values())
    return {
        "total": total,
        "parsed": parsed,
        "bad": bad,
        "monthly": monthly,
        "monthly_enterprise": monthly_enterprise,
        "monthly_licence": monthly_licence,
        "enterprise_total": len(ent_first),
        "licence_total": len(lic_first),
        "by_type": by_type,
        "date_min": date_min,
        "date_max": date_max,
        "sample_rows": sample_rows,
        "future_rows": future_rows,
    }


def aggregate_snapshots(paths, *, date_col=None, type_col=None, limit=None):
    """读取一个或多个快照文件并完成列识别与月度聚合（纯函数）。

    返回 {"columns", "date_col", "type_col", "stats", "warnings"}。
    供 update() 与测试复用；结构与旧 main 的处理段一致。
    """

    rows_iter = iter_rows(paths, limit=limit)
    first = next(rows_iter, None)
    if first is None:
        raise ValueError("数据文件为空，无法处理。")
    columns_seen = list(first.keys())
    used_date_col = date_col or guess_column(columns_seen, DATE_PATTERNS)
    used_type_col = None if type_col is False else (type_col or guess_column(columns_seen, TYPE_PATTERNS))

    def all_rows():
        yield first
        yield from rows_iter

    stats = aggregate(all_rows(), used_date_col, used_type_col)
    warnings = []
    if stats["future_rows"]:
        warnings.append(f"{len(stats['future_rows'])} 行发证月份晚于当前月份，隔离并保留原始记录。")
    if not used_date_col:
        warnings.append("未识别到日期列，无法按月聚合（可用 --date-col 指定）。")
    elif stats["bad"]:
        warnings.append(f"{stats['bad']:,} 行日期无法解析，已跳过（可用 --date-col 换列）。")
    if not used_type_col:
        warnings.append("未识别到类型列，跳过按类型明细。")
    return {
        "columns": columns_seen,
        "date_col": used_date_col,
        "type_col": used_type_col,
        "stats": stats,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# 审计文件输出（与 fetch_ded_license.py 相同结构）
# --------------------------------------------------------------------------

def write_monthly(path, monthly):
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["month", "new_licenses"])
        for key in sorted(monthly):
            writer.writerow([key, monthly[key]])


def write_monthly_counts(path, monthly, monthly_enterprise, monthly_licence):
    """三种口径的月度序列：记录数 / 当月有发证活动的企业数 / 当月新发执照数。"""
    months = sorted(set(monthly) | set(monthly_enterprise) | set(monthly_licence))
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["month", "records", "enterprises", "licences"])
        for key in months:
            writer.writerow(
                [key, monthly.get(key, 0), monthly_enterprise.get(key, 0), monthly_licence.get(key, 0)]
            )


def write_monthly_by_type(path, by_type):
    with open(path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["month", "license_type", "count"])
        for (month, tval), count in sorted(by_type.items()):
            writer.writerow([month, tval, count])


def write_schema_report(path, columns, stats, date_col, type_col, warnings):
    lines = [
        "DED 企业注册主表 字段与数据质量报告",
        "=" * 50,
        f"总行数: {stats['total']:,}",
        (f"日期可解析: {stats['parsed']:,} "
         f"({(stats['parsed'] / stats['total'] * 100):.1f}%)")
        if stats["total"] else "日期可解析: 0",
        f"日期不可解析: {stats['bad']:,}",
        f"日期范围: {stats['date_min']} ~ {stats['date_max']}",
        f"日期列(自动识别): {date_col or '(未识别)'}",
        f"类型列(自动识别): {type_col or '(未识别)'}",
        "",
        "字段列表:",
    ]
    for col in columns:
        lines.append(f"  - {col}")
    if warnings:
        lines += ["", "警告:"]
        lines += [f"  - {w}" for w in warnings]
    lines += ["", "样例数据(前3行):"]
    for row in stats["sample_rows"]:
        lines.append("  " + json.dumps(row, ensure_ascii=False)[:500])
    with open(path, "w", encoding="utf-8", newline="") as target:
        target.write("\n".join(lines) + "\n")


def build_manifest(out_dir, **kwargs):
    manifest = {"generated_at": datetime.now().isoformat(timespec="seconds")}
    manifest.update(kwargs)
    with open(out_dir / "fetch_manifest.json", "w", encoding="utf-8") as target:
        json.dump(manifest, target, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# 官方数字与库行转换
# --------------------------------------------------------------------------

def _month_end_date(month_key: str) -> object:
    """'YYYY-MM' -> 月末 date（DuckDB DATE 列用）。"""
    year, month = int(month_key[:4]), int(month_key[5:7])
    return (
        datetime(year, month, calendar.monthrange(year, month)[1]).date()
    )


def _ensure_official_news_tables(con) -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {OFFICIAL_NEWS_TABLE} (
            source_url VARCHAR NOT NULL,
            published_at DATE,
            period_label VARCHAR NOT NULL,
            period_kind VARCHAR NOT NULL,
            month DATE,
            value BIGINT NOT NULL,
            headline VARCHAR,
            snippet VARCHAR,
            retrieved_at TIMESTAMP NOT NULL,
            PRIMARY KEY (source_url, period_label, value)
        )
        """
    )
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {OFFICIAL_NEWS_STATE_TABLE} (
            state_key VARCHAR PRIMARY KEY,
            state_value VARCHAR NOT NULL
        )
        """
    )


def _official_news_scan_start(con) -> date:
    _ensure_official_news_tables(con)
    row = con.execute(
        f"SELECT state_value FROM {OFFICIAL_NEWS_STATE_TABLE} "
        "WHERE state_key = 'last_successful_scan'"
    ).fetchone()
    if row:
        last_scan = date.fromisoformat(str(row[0]))
        return last_scan - timedelta(days=45)
    return date(2020, 1, 1)


def _store_official_news_candidates(con, observations: list[dict]) -> int:
    retrieved_at = datetime.now().replace(microsecond=0)
    rows = []
    for item in observations:
        month_key = str(item["month"])
        month = _month_end_date(month_key) if month_key else None
        rows.append(
            (
                item["source_url"],
                item.get("published_at"),
                f"{item['period']} {item['year']}",
                item["period_kind"],
                month,
                int(item["value"]),
                item.get("headline"),
                item.get("snippet"),
                retrieved_at,
            )
        )
    if rows:
        con.executemany(
            f"""
            INSERT INTO {OFFICIAL_NEWS_TABLE}
            (source_url, published_at, period_label, period_kind, month, value,
             headline, snippet, retrieved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_url, period_label, value) DO UPDATE SET
                published_at = excluded.published_at,
                period_kind = excluded.period_kind,
                month = excluded.month,
                headline = excluded.headline,
                snippet = excluded.snippet,
                retrieved_at = excluded.retrieved_at
            """,
            rows,
        )
    return len(rows)


def _automatic_official_values(con) -> dict[str, int]:
    """Return only unambiguous observations extracted from official news."""

    values: dict[str, int] = {}
    rows = con.execute(
        f"""
        SELECT month, COUNT(DISTINCT value) AS value_count, MIN(value) AS value
        FROM {OFFICIAL_NEWS_TABLE}
        WHERE month IS NOT NULL
        GROUP BY month
        HAVING COUNT(DISTINCT value) = 1
           AND COUNT(DISTINCT period_kind) = 1
        ORDER BY month
        """
    ).fetchall()
    for period, _, value in rows:
        month_key = period.strftime("%Y-%m")
        values[month_key] = int(value)
    return values


def _ded_monthly_rows(stats, official: dict[str, int]) -> list[dict[str, object]]:
    """把聚合结果与官方数字摊平成 ded_monthly 长表行。"""

    rows: list[dict[str, object]] = []
    series_map = {
        "records": stats["monthly"],
        "enterprises": stats["monthly_enterprise"],
        "licences": stats["monthly_licence"],
    }
    for series, counter in series_map.items():
        for month_key, value in sorted(counter.items()):
            rows.append(
                {
                    "month": _month_end_date(month_key),
                    "series": series,
                    "value": float(value),
                }
            )
    for month_key, value in sorted(official.items()):
        rows.append(
            {
                "month": _month_end_date(month_key),
                "series": "official_new_licenses",
                "value": float(value),
            }
        )
    return rows


def _ded_by_type_rows(stats) -> list[dict[str, object]]:
    """by_type 摊平成 ded_monthly_by_type 行。

    'unknown' 月份（日期无法解析的行）无法映射到 DATE 列，只留在审计 CSV 中。
    """

    rows: list[dict[str, object]] = []
    for (month_key, legal_form), count in sorted(stats["by_type"].items()):
        if month_key == "unknown":
            continue
        rows.append(
            {
                "month": _month_end_date(month_key),
                "legal_form": legal_form,
                "records": count,
            }
        )
    return rows


# --------------------------------------------------------------------------
# 事务上下文
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# 库查询 → 月度_DED 输入（merge 用）
# --------------------------------------------------------------------------


def _sheet_spec(con) -> dict[str, Any]:
    series_names = {
        "records": "迪拜:DED:当月快照记录数",
        "enterprises": "迪拜:当月有发证活动的企业数(企业号筛重)",
        "licences": "迪拜:当月新发执照数(执照号筛重)",
        "official_new_licenses": "迪拜:新发执照数(官方口径)",
    }
    periods = {}
    for period, series, value in con.execute(
        "SELECT month, series, value FROM ded_monthly ORDER BY month"
    ).fetchall():
        periods.setdefault(period, {})[series_names[series]] = value
    rows = list(periods.items())
    return {
        "name": SHEET_NAME,
        "title": "DED 迪拜商业注册月度指标",
        "indicators": list(series_names.values()),
        "rows": rows,
    }


def _latest_snapshot() -> Path:
    """--skip-download 路径：取 raw/ 下最新快照（与原脚本一致）。"""
    snaps = sorted(RAW.glob("commerce_registry_*"))
    if not snaps:
        raise FileNotFoundError(f"raw/ 下没有快照，无法跳过下载: {RAW}")
    return snaps[-1]


def _download_snapshots() -> tuple[list[Path], list[str]]:
    """完整下载流程（data.dubai dataset 460521）。

    返回 (本地快照路径列表, 源文件直链列表)（直链供清单记录）。
    """

    opener = build_opener()
    files = fetch_data_dubai_files(opener, DATASET_ID, headers={}, prefer="csv")
    for item in files:
        print(f"  {item['file_name']} ({format_bytes(item['file_size'])})")
    snapshots = []
    file_urls = []
    for item in files:
        name = Path(urllib.parse.urlparse(item["file_url"]).path).name or "datafile"
        dest = RAW / name
        print(f"下载到: {name}")
        final_url, ctype = stream_to_file(
            opener, item["file_url"], dest, headers={}, timeout=180, retries=4
        )
        print(f"下载完成: {format_bytes(dest.stat().st_size)}")
        snapshots.append(dest)
        file_urls.append(item["file_url"])
    if not snapshots:
        raise RuntimeError("没有可处理的快照文件。")
    return snapshots, file_urls


def update(
    con, *, force: bool = False, skip_download: bool = False
) -> dict[str, object]:
    """下载（或复用）快照 → 月度聚合 → 审计文件 → 事务内入库。

    异常直接抛出由总控记录；skip_download=True 时使用 raw/ 最新快照重算。
    """

    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    snapshots: list[Path]
    if skip_download:
        snapshots = [_latest_snapshot()]
        print(f"使用已有快照: {snapshots[0].name}")
        file_urls = ["local"]
    else:
        snapshots, file_urls = _download_snapshots()

    result = aggregate_snapshots(snapshots)
    stats = result["stats"]
    warnings = result["warnings"]
    (OUT / "future_issue_dates.json").write_text(
        json.dumps(stats["future_rows"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    news_scan = None
    if not skip_download:
        scan_start = _official_news_scan_start(con)
        news_scan = fetch_official_news.discover_official_news(start=scan_start)
        for url in news_scan.get("articles_without_text", []):
            warnings.append(f"媒体办原文没有正文，未提取指标: {url}")

    # 审计文件（本地，结构照旧）
    write_monthly(OUT / "monthly_new_licenses.csv", stats["monthly"])
    write_monthly_counts(
        OUT / "monthly_counts.csv",
        stats["monthly"],
        stats["monthly_enterprise"],
        stats["monthly_licence"],
    )
    if result["type_col"]:
        write_monthly_by_type(OUT / "monthly_by_type.csv", stats["by_type"])
    write_schema_report(
        OUT / "schema_report.txt",
        result["columns"],
        stats,
        result["date_col"],
        result["type_col"],
        warnings,
    )
    build_manifest(
        OUT,
        dataset_id=DATASET_ID,
        source_urls=file_urls,
        snapshot_files=[s.name for s in snapshots],
        snapshot_sha256=[sha256_file(s) for s in snapshots],
        snapshot_sizes=[s.stat().st_size for s in snapshots],
        row_count=stats["total"],
        parsed_dates=stats["parsed"],
        unparsed_dates=stats["bad"],
        enterprise_count=stats["enterprise_total"],
        licence_count=stats["licence_total"],
        date_col_used=result["date_col"],
        type_col_used=result["type_col"],
        date_min=stats["date_min"],
        date_max=stats["date_max"],
        warnings=warnings,
    )

    by_type_rows = _ded_by_type_rows(stats)
    with _transaction(con):
        _ensure_official_news_tables(con)
        if news_scan is not None:
            _store_official_news_candidates(con, news_scan["observations"])
            con.execute(
                f"DELETE FROM {OFFICIAL_NEWS_STATE_TABLE} "
                "WHERE state_key = 'last_successful_scan'"
            )
            con.execute(
                f"INSERT INTO {OFFICIAL_NEWS_STATE_TABLE} VALUES (?, ?)",
                ["last_successful_scan", news_scan["scanned_through"].isoformat()],
            )
        official = _automatic_official_values(con)
        if not official:
            raise ValueError(
                "官方新闻候选表中没有无冲突的执照观测值，拒绝写入空官方序列"
            )
        monthly_rows = _ded_monthly_rows(stats, official)
        replace(con, MONTHLY_TABLE, monthly_rows)
        replace(con, BY_TYPE_TABLE, by_type_rows)

    print()
    print("=" * 60)
    print(f"总行数      : {stats['total']:,}")
    print(f"日期列      : {result['date_col'] or '(未识别)'}")
    print(f"类型列      : {result['type_col'] or '(未识别)'}")
    print(f"日期范围    : {stats['date_min']} ~ {stats['date_max']}")
    print("=" * 60)

    return {
        "status": "ok",
        "rows": len(monthly_rows) + len(by_type_rows),
        "note": (
            f"快照 {len(snapshots)} 个，{stats['total']:,} 行；月度三口径 "
            f"{len(stats['monthly'])} 个月、分类型 {len(by_type_rows)} 行；"
            f"官方数字 {len(official)} 个期间；"
            + (
                f"媒体办扫描 {news_scan['pages']} 页、"
                f"提取 {len(news_scan['observations'])} 个候选；"
                f"无正文新闻 {len(news_scan.get('articles_without_text', []))} 条（见审计告警）"
                if news_scan is not None
                else "跳过媒体办扫描（复用 DuckDB 候选）"
            )
        ),
    }


def merge(workbook_path: Path) -> dict[str, object]:
    """从正式库重建「月度_DED」，使用共享原子写表工具。

    写入前在 data/UAE/raw/ded/backups/ 留时间戳备份；Excel 占用时抛出明确错误。
    """

    target = Path(workbook_path).resolve()
    if not target.exists():
        raise FileNotFoundError(f"工作簿不存在: {target}")

    con = connect(read_only=True)
    try:
        spec = _sheet_spec(con)
        spec["metadata"] = read_indicator_metadata(con, spec["indicators"])
    finally:
        con.close()
    if not spec["rows"]:
        raise RuntimeError("ded_monthly 数据为空，无可写入内容。")

    # 写入前备份（遵循项目惯例；备份目录改到 data/UAE/raw/ded/backups/）
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"阿联酋_before_ded_{stamp}.xlsx"
    shutil.copy2(target, backup)

    counts = write_indicator_sheets(target, [spec])
    return {"status": "ok", "note": f"sheet「{SHEET_NAME}」更新 {counts[SHEET_NAME]} 行"}
