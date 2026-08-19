#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 DET/迪拜媒体办新闻稿提取官方执照数字（半自动，人工确认后入库）。

逻辑平移自 data/ded_license/fetch_official_news.py，唯一差异：
- 所有路径指向 data/UAE/raw/ded/（news_urls.txt / official_pending.csv /
  official_ded_monthly.csv 均在此目录）。

流程
----
1. 输入新闻 URL（--url 单个 / --urls-file 批量 / 默认 news_urls.txt）；
2. 抓取正文，用正则提取"X new business licences in [Month] [Year]"类数字；
3. 输出 official_pending.csv（建议行：month, value, note, source_url, 原文片段）；
4. 人工检查后 --apply 合并进 official_ded_monthly.csv（同月已有值则跳过，防覆盖）。

说明
----
官方不提供结构化月度数据，数字以新闻稿文字形式发布；本脚本把提取过程半自动化，
最终入库前必须人工确认（新闻稿措辞口径差异大：月度/季度/年度/H1/H2）。
"""

import argparse
import csv
import html
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent
RAW_DED = DATA_DIR / "raw" / "ded"
DEFAULT_URLS_FILE = RAW_DED / "news_urls.txt"
DEFAULT_PENDING = RAW_DED / "official_pending.csv"
DEFAULT_OFFICIAL = RAW_DED / "official_ded_monthly.csv"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# 数字 + 期间 的模式（按优先级：带月份 > 带季度/半年 > 仅年份）
PATTERNS = [
    re.compile(r"issued?\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+in\s+([A-Z][a-z]+)\s+(\d{4})", re.I),
    re.compile(r"issues?\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+in\s+([A-Z][a-z]+)\s+(\d{4})", re.I),
    re.compile(r"([\d,]+)\s+new\s+business\s+licen[cs]es?\s+(?:were\s+)?issued\s+in\s+([A-Z][a-z]+)\s+(\d{4})", re.I),
    re.compile(r"([\d,]+)\s+new\s+licen[cs]es?\s+in\s+([A-Z][a-z]+)\s+(\d{4})", re.I),
    re.compile(r"issued?\s+([\d,]+)\s+new\s+business\s+licen[cs]es?\s+in\s+((?:H|Q)[12])\s+(\d{4})", re.I),
    re.compile(r"([\d,]+)\s+new\s+business\s+licen[cs]es?\s+in\s+(\d{4})", re.I),
    re.compile(r"issued?\s+([\d,]+)\s+new\s+licen[cs]es?\s+in\s+(\d{4})", re.I),
]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="提取官方执照数字（人工确认后入库）")
    parser.add_argument("--url", default=None, help="单个新闻 URL")
    parser.add_argument("--urls-file", default=str(DEFAULT_URLS_FILE), help="URL 列表文件（每行一个）")
    parser.add_argument("--pending", default=str(DEFAULT_PENDING), help="待确认 CSV 输出路径")
    parser.add_argument("--official", default=str(DEFAULT_OFFICIAL), help="正式官方数字 CSV")
    parser.add_argument("--apply", action="store_true", help="把 pending 合并进 official（同月已有值跳过）")
    parser.add_argument("--force", action="store_true", help="--apply 时覆盖同月已有值")
    return parser.parse_args(argv)


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError:
        # 证书链不全的站点（如部分阿联酋小站）：降级为不校验证书重试一次
        import ssl
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
            raw = response.read().decode("utf-8", errors="replace")
    # 去 script/style，去标签
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(re.sub(r"\s+", " ", raw))


def period_to_month(period, year):
    """'January'->'2025-01'；'H1'->'2025-06'；'Q1'->'2025-03'；仅年份->'2025-12'。"""
    key = period.lower()
    year = int(year)
    if key == "full_year":
        return f"{year:04d}-12"
    if key in MONTHS:
        return f"{year:04d}-{MONTHS[key]:02d}"
    if key == "h1":
        return f"{year:04d}-06"
    if key == "h2":
        return f"{year:04d}-12"
    if key.startswith("q"):
        return f"{year:04d}-{int(key[1]) * 3:02d}"
    return f"{year:04d}-12"


def extract_from_text(text, url):
    """返回所有命中：[{month, value, period, note, snippet}]"""
    hits = []
    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            value = int(m.group(1).replace(",", ""))
            if len(m.groups()) >= 3:
                period, year = m.group(2), m.group(3)
            else:
                period, year = "full_year", m.group(2)
            month = period_to_month(period, year)
            note = f"官方新闻稿：{period} {year}新发{value:,}张"
            if period == "full_year":
                note = f"官方新闻稿：{year}全年新发{value:,}张"
            snippet = text[max(0, m.start() - 80): m.end() + 80].strip()
            hits.append({
                "month": month,
                "value": value,
                "period": period,
                "year": year,
                "note": note,
                "snippet": snippet[:200],
            })
    # 去重（同 month+value）
    seen = set()
    unique = []
    for h in hits:
        key = (h["month"], h["value"])
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return unique


def load_urls(path):
    if not Path(path).exists():
        return []
    urls = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def main(argv=None):
    args = parse_args(argv)
    urls = []
    if args.url:
        urls.append(args.url)
    urls += load_urls(args.urls_file)
    if not urls:
        raise SystemExit(f"没有可处理的 URL（--url 或 {args.urls_file}）")

    if args.apply:
        apply_pending(args.pending, args.official, args.force)
        return

    rows = []
    for url in urls:
        try:
            text = fetch_text(url)
        except Exception as exc:
            print(f"! 抓取失败 {url}: {exc}")
            continue
        hits = extract_from_text(text, url)
        if not hits:
            print(f"- 未提取到数字 {url}")
            continue
        for h in hits:
            rows.append({
                "month": h["month"],
                "official_new_licenses": h["value"],
                "note": h["note"],
                "source_url": url,
                "snippet": h["snippet"],
            })
            print(f"  {h['month']}: {h['value']:,}  ({url})")
            print(f"    原文: …{h['snippet']}…")

    if rows:
        with open(args.pending, "w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=["month", "official_new_licenses", "note", "source_url", "snippet"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n已输出 {len(rows)} 条待确认 → {args.pending}")
        print("人工检查后运行：python -u fetch_official_news.py --apply")


def apply_pending(pending_path, official_path, force):
    if not Path(pending_path).exists():
        raise SystemExit(f"待确认文件不存在: {pending_path}")
    existing = {}
    if Path(official_path).exists():
        with open(official_path, "r", encoding="utf-8-sig") as source:
            for row in csv.DictReader(source):
                existing[row["month"]] = row
    added = skipped = 0
    with open(pending_path, "r", encoding="utf-8-sig") as source:
        pending = list(csv.DictReader(source))
    for row in pending:
        month = row["month"]
        if month in existing and not force:
            skipped += 1
            continue
        existing[month] = {
            "month": month,
            "official_new_licenses": row["official_new_licenses"],
            "note": row["note"],
            "source_url": row["source_url"],
        }
        added += 1
    fields = ["month", "official_new_licenses", "note", "source_url"]
    with open(official_path, "w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for month in sorted(existing):
            row = existing[month]
            writer.writerow({k: row.get(k) for k in fields})
    print(f"合并完成：新增 {added}，跳过（同月已有）{skipped} → {official_path}")


if __name__ == "__main__":
    main()