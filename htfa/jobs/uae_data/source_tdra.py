"""TDRA 电信订阅统计（source_tdra.py）——月度入库。

数据来源：TDRA（Telecommunications and Digital Government Regulatory Authority, UAE）
官方 Open Data 目录 https://tdra.gov.ae/en/open-data/data-sets 。
目录内「Phone and internet subscriptions」系列各数据集提供单个 XLSX 工作簿，
底层为 2011-01 起的逐月全历史（sheet "Monthly statistics"：日期 + 指标值），
每次发布更新到当年 12 月。本模块收录其中 9 个订阅类指标（电话/固定/宽带/互联网），
不含手机网络体验基准类（Indoor/Outdoor benchmarking）。

- 原始件：`data/UAE/raw/tdra/<slug>.xlsx`（9 个文件，脚本自动从目录页发现并下载）。
- 入库表：`tdra_telecom_monthly`（period, indicator, value, source_file 长表）。
- 目标 sheet：`月度_TDRA`（经 write_indicator_sheet.ps1 重建）。

单位：订阅数/线数为「户/条」，per-100-inhabitants 为「户/百人」。
"""

from __future__ import annotations

from types import SimpleNamespace

import html
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

from .db import transaction
from .paths import DATA_DIR


import requests
from openpyxl import load_workbook

from . import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "tdra"
TABLE = "tdra_telecom_monthly"
SOURCE_NAME = "TDRA Open Data"
FREQUENCY = "月"
INDUSTRY = "电信"
TARGET_SHEET = "月度_TDRA"
DICTIONARY_SHEET = "指标字典"

# 每个数据项：slug（即磁盘文件名）→（官方英文题名, 中文指标名, 单位, 类型）
ITEMS: dict[str, tuple[str, str, str, str]] = {
    "active-mobile-subscriptions": (
        "Active Mobile Subscriptions",
        "阿联酋:TDRA活跃移动订阅数",
        "户",
        "存量",
    ),
    "post-paid-subscriptions": (
        "Post paid Subscriptions",
        "阿联酋:TDRA后付费移动订阅数",
        "户",
        "存量",
    ),
    "pre-paid-subscriptions": (
        "Pre-paid Subscriptions",
        "阿联酋:TDRA预付费移动订阅数",
        "户",
        "存量",
    ),
    "broadband-subscriptions": (
        "Broadband Subscriptions",
        "阿联酋:TDRA宽带订阅数",
        "户",
        "存量",
    ),
    "broadband-per-100": (
        "Broadband Internet Subscriptions per 100 inhabitants",
        "阿联酋:TDRA每百人宽带订阅数",
        "户/百人",
        "存量",
    ),
    "number-of-fixed-lines": (
        "Number of Fixed Lines",
        "阿联酋:TDRA固定电话线数",
        "条",
        "存量",
    ),
    "fixed-lines-per-100": (
        "Fixed lines per 100 inhabitants",
        "阿联酋:TDRA每百人固定电话线数",
        "条/百人",
        "存量",
    ),
    "internet-subscriptions": (
        "Internet Subscriptions",
        "阿联酋:TDRA互联网订阅数",
        "户",
        "存量",
    ),
    "mobile-per-100": (
        "Mobile Subscriptions per 100 inhabitants",
        "阿联酋:TDRA每百人移动订阅数",
        "户/百人",
        "存量",
    ),
}

HOST = "https://tdra.gov.ae"
DATASETS_PAGE = HOST + "/en/open-data/data-sets"

_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    period      DATE                  NOT NULL,
    indicator   VARCHAR               NOT NULL,
    value       DECIMAL(20, 4),
    source_file VARCHAR,
    PRIMARY KEY (period, indicator)
)
"""


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


def _session() -> requests.Session:
    """带语言 Cookie 的会话（TDRA 站点默认阿拉伯语，需 en Cookie）。"""
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120 Safari/537.36"
    )
    session.headers["Accept-Language"] = "en-US,en;q=0.9"
    session.cookies.update({"website#lang": "en", "shell#lang": "en"})
    return session


def _discover_downloads(
    session: requests.Session,
) -> dict[str, str]:
    """按官方指标标题发现媒体直链，映射到项目内部指标标识。

    页面卡片形如：
        <div class="aegov-card ...">
          <h6 class="text-h6 flex-1">Active Mobile Subscriptions</h6>
          ...
          <a onclick="countDownloads('<slug>', ...)" href="/-/media/Open-Data/<...>">
        </div>
    """
    response = session.get(DATASETS_PAGE, timeout=60)
    response.raise_for_status()
    found: dict[str, str] = {}
    for block in re.split(r'<div class="aegov-card ', response.text)[1:]:
        title_m = re.search(r'<h6\b[^>]*>(.*?)</h6>', block, re.S)
        href_m = re.search(r'href="(/-/media/Open-Data/[^"]+\.ashx[^"]*)"', block)
        if title_m and href_m:
            title = " ".join(html.unescape(title_m.group(1)).split()).casefold()
            for slug, (official_title, *_) in ITEMS.items():
                if title == " ".join(official_title.split()).casefold():
                    found[slug] = urljoin(HOST, html.unescape(href_m.group(1)))
    return found


def _download_all(
    *,
    skip_download: bool = False,
) -> None:
    """在线刷新全部工作簿；显式离线模式要求九份原始文件齐全。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if skip_download:
        missing = [slug for slug in ITEMS if not (RAW_DIR / f"{slug}.xlsx").is_file()]
        if missing:
            raise FileNotFoundError(
                "skip-download 但以下 TDRA 原始件缺失: " + ", ".join(missing)
            )
        return
    with _session() as session:
        discovered = _discover_downloads(session)
        for slug in ITEMS:
            url = discovered.get(slug)
            if url is None:
                raise ValueError(f"TDRA 目录页未发现数据集: {slug}")
            response = session.get(url, timeout=120)
            response.raise_for_status()
            if not response.content.startswith(b"PK"):
                raise ValueError(f"TDRA 下载疑似非 XLSX: {slug} ({response.status_code})")
            path = RAW_DIR / f"{slug}.xlsx"
            temporary = path.with_name(f".{slug}.tmp.xlsx")
            try:
                temporary.write_bytes(response.content)
                if not _parse_workbook(temporary):
                    raise ValueError(f"TDRA 工作簿没有月度数据: {slug}")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 解析 / 入库
# ---------------------------------------------------------------------------


def _normalize_value(value: object) -> float | None:
    """TDRA 单元格部分数值以带千分位的字符串存储（如 '16,716,782 '），统一转 float。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = (
            value.replace(",", "")
            .replace("\u2009", "")  # 窄空格
            .replace("\u00a0", "")  # 不换行空格
            .replace(" ", "")
            .strip()
        )
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _parse_workbook(path: Path) -> list[tuple[date, float]]:
    """解析 'Monthly statistics' sheet：A 列日期、B 列数值，跳过空行/坏值。"""
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook.worksheets[0]
    pairs: list[tuple[date, float]] = []
    for cell_a, cell_b in sheet.iter_rows(min_row=2, max_col=2):
        period_value, value = cell_a.value, cell_b.value
        if not isinstance(period_value, datetime):
            continue
        number = _normalize_value(value)
        if number is None:
            continue
        pairs.append((period_value.date(), number))
    workbook.close()
    pairs.sort(key=lambda item: item[0])
    return pairs


def _read_rows() -> list[dict]:
    """把全部指标展开为 (period, indicator, value) 长表行。"""
    rows: list[dict] = []
    for slug, (_, indicator, _, _) in ITEMS.items():
        path = RAW_DIR / f"{slug}.xlsx"
        if not path.is_file():
            raise FileNotFoundError(f"TDRA 原始件缺失: {path}")
        for period, value in _parse_workbook(path):
            rows.append(
                {
                    "period": period,
                    "indicator": indicator,
                    "value": value,
                    "source_file": path.name,
                }
            )
    return rows


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": indicator,
            "frequency": FREQUENCY,
            "unit": unit,
            "source": SOURCE_NAME,
            "type": kind,
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for _, (_, indicator, unit, kind) in ITEMS.items()
    ]


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载 -> 解析 -> 整表替换入 tdra_telecom_monthly。"""
    download_note = ""
    _download_all(skip_download=skip_download)
    if not skip_download:
        # TDRA keeps stable workbook names while updating the latest
        # observations in place; refresh all discovered files online.
        download_note = "已在线刷新 TDRA 工作簿"
    rows = _read_rows()
    if not rows:
        raise ValueError("tdra_telecom_monthly 输入为空，拒绝入库")

    with transaction(con):
        db.ensure(con, TABLE, _TABLE_DDL)
        db.replace(con, TABLE, rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    periods = sorted({row["period"] for row in rows})
    counts = {indicator: 0 for _, (_, indicator, _, _) in ITEMS.items()}
    for row in rows:
        counts[row["indicator"]] += 1
    note = (
        f"{len(ITEMS)} 个指标，{len(periods)} 个月"
        f"（{periods[0].isoformat()} 至 {periods[-1].isoformat()}），"
        f"共 {len(rows)} 行"
    )
    if download_note:
        note += f"；{download_note}"
    return {"status": "ok", "rows": len(rows), "note": note}


# ---------------------------------------------------------------------------
# 合并回 Excel
# ---------------------------------------------------------------------------


def merge(workbook_path: Path) -> dict:
    """把 tdra_telecom_monthly 写回 阿联酋.xlsx 的 月度_TDRA sheet。"""
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_indicator_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    from ._excel_helpers import payload_json_file, records_latest_first, run_powershell_sheet_writer

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, indicator, value "
            "FROM tdra_telecom_monthly ORDER BY period"
        ).fetchall()
    finally:
        con.close()

    INDICATOR_ORDER = {indicator: index for index, (_, (_, indicator, _, _)) in enumerate(ITEMS.items())}
    by_period: dict[str, dict] = {}
    for period, indicator, value in db_rows:
        key = period.strftime("%Y-%m")
        item = by_period.setdefault(key, {"values": [None] * len(ITEMS)})
        item["values"][INDICATOR_ORDER[indicator]] = value
    observations = [
        SimpleNamespace(period=period, values=tuple(item["values"]))
        for period, item in sorted(by_period.items())
    ]
    if not observations:
        raise ValueError("tdra_telecom_monthly is empty; nothing to merge")

    payload = {
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "source_label": SOURCE_NAME,
        "number_format": "#,##0.##",
        "column_width": 34,
        "period_format": "month",
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": FREQUENCY,
        "unit": "见各列",
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": indicator, "unit": unit, "type": kind, "industry": INDUSTRY}
            for _, (_, indicator, unit, kind) in ITEMS.items()
        ],
        "records": records_latest_first(observations),
    }
    with payload_json_file(payload, prefix=".tdra-sheet-", directory=DATA_DIR) as payload_path:
        run_powershell_sheet_writer(helper_path, workbook_path, payload_path, TARGET_SHEET)
    return {
        "status": "ok",
        "note": f"{len(observations)} 个月写入 {TARGET_SHEET}",
    }
