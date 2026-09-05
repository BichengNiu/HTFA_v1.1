"""TDRA 电信订阅统计（source_tdra.py）——月度入库。

数据来源：TDRA（Telecommunications and Digital Government Regulatory Authority, UAE）
官方 Open Data 目录 https://tdra.gov.ae/en/open-data/data-sets 。
目录内「Phone and internet subscriptions」系列各数据集提供单个 XLSX 工作簿，
底层为 2011-01 起的逐月全历史（sheet "Monthly statistics"：日期 + 指标值），
每次发布更新到当年 12 月。本模块收录其中 9 个订阅类指标（电话/固定/宽带/互联网），
不含手机网络体验基准类（Indoor/Outdoor benchmarking）。

- 原始件：`data/UAE/raw/tdra/<slug>.xlsx`（9 个文件，脚本自动从目录页发现并下载）。
- 入库表：`tdra_telecom_monthly`（period, indicator, value, source_file 长表）。
- 目标 sheet：`月度_TDRA`（经 write_tdra_sheet.ps1 重建）。

单位：订阅数/线数为「户/条」，per-100-inhabitants 为「户/百人」。
"""

from __future__ import annotations

import io
import re
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from .paths import DATA_DIR, SCRIPTS_DIR


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

# 目录页已知的直链（作为发现失败时的回退；slug → media 路径尾段）
_FALLBACK_MEDIA = {
    "active-mobile-subscriptions": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Active-Mobile-Subscriptions-Dec-2025.ashx"
    ),
    "post-paid-subscriptions": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Post-paid-Subscriptions-En--Dec-2025.ashx"
    ),
    "pre-paid-subscriptions": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Pre-paid-Subsriptions-En-Dec-2025.ashx"
    ),
    "broadband-subscriptions": (
        "Dec-2024/English/Broadband-Subscriptions-En-Dec-2024.ashx"
    ),
    "broadband-per-100": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Broadband-Internet-Subscriptions-per-100-inhabitants-En-Dec-2025.ashx"
    ),
    "number-of-fixed-lines": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Number-of--Fixed-Lines-En-Dec-2025.ashx"
    ),
    "fixed-lines-per-100": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Fixed-lines-per-100-inhabitants-En-Dec-2025.ashx"
    ),
    "internet-subscriptions": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Internet-Subscriptions-En-Dec-2025.ashx"
    ),
    "mobile-per-100": (
        "Phone-and-internet-subscriptions/Phone-and-Internet-Subscriptions-2025/"
        "Mobile-Subscriptions-per-100-inhabitants-En-Dec-2025.ashx"
    ),
}

HOST = "https://tdra.gov.ae"
DATASETS_PAGE = HOST + "/en/open-data/data-sets"
MEDIA_PREFIX = HOST + "/-/media/Open-Data/"

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
    """抓取数据集目录页，把 data-item slug → media 直链路径映射出来。

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
        item_m = re.search(r'data-item="([^"]+)"', block)
        href_m = re.search(r'href="(/-/media/Open-Data/[^"]+\.ashx[^"]*)"', block)
        if item_m and href_m:
            slug = item_m.group(1)
            if slug not in ITEMS:
                continue
            found[slug] = href_m.group(1).lstrip("/")
    return found


def _download_all(
    *,
    force: bool = False,
    skip_download: bool = False,
) -> dict[str, Path]:
    """把 9 个指标的工作簿下载/复用为 raw/tdra/<slug>.xlsx。

    返回 slug → 本地文件路径 映射；已有文件且未 force 时直接复用。
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target: dict[str, Path] = {}
    missing = [
        slug for slug in ITEMS
        if force or not (RAW_DIR / f"{slug}.xlsx").is_file()
    ]
    if missing and skip_download:
        raise FileNotFoundError(
            "skip-download 但以下 TDRA 原始件缺失: "
            + ", ".join(missing)
        )
    if missing:
        session = _session()
        discovered = _discover_downloads(session)
        for slug in missing:
            suffix = discovered.get(slug) or _FALLBACK_MEDIA[slug]
            url = MEDIA_PREFIX + suffix
            response = session.get(url, timeout=120)
            response.raise_for_status()
            if not response.content.startswith(b"PK") or not response.headers.get(
                "content-disposition", ""
            ):
                raise ValueError(f"TDRA 下载疑似非 XLSX: {slug} ({response.status_code})")
            (RAW_DIR / f"{slug}.xlsx").write_bytes(response.content)
    for slug in ITEMS:
        target[slug] = RAW_DIR / f"{slug}.xlsx"
    return target


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


@contextmanager
def _transaction(con) -> Iterator[None]:
    transaction = con.begin()
    try:
        yield
    except BaseException:
        transaction.rollback()
        raise
    else:
        transaction.commit()


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载 -> 解析 -> 整表替换入 tdra_telecom_monthly。"""
    _download_all(force=force, skip_download=skip_download)
    rows = _read_rows()
    if not rows:
        raise ValueError("tdra_telecom_monthly 输入为空，拒绝入库")

    with _transaction(con):
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
    return {"status": "ok", "rows": len(rows), "note": note}


# ---------------------------------------------------------------------------
# 合并回 Excel
# ---------------------------------------------------------------------------


def merge(workbook_path: Path) -> dict:
    """把 tdra_telecom_monthly 写回 阿联酋.xlsx 的 月度_TDRA sheet。"""
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_tdra_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    from ._excel_helpers import payload_json_file, records_latest_first, run_powershell_sheet_writer

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, indicator, value, source_file "
            "FROM tdra_telecom_monthly ORDER BY period"
        ).fetchall()
    finally:
        con.close()

    INDICATOR_ORDER = {indicator: index for index, (_, (_, indicator, _, _)) in enumerate(ITEMS.items())}
    by_period: dict[str, dict] = {}
    for period, indicator, value, source_file in db_rows:
        key = period.strftime("%Y-%m")
        item = by_period.setdefault(key, {"values": [None] * len(ITEMS), "source_file": source_file})
        item["values"][INDICATOR_ORDER[indicator]] = value
    class _Obs:
        def __init__(self, period, values):
            self.period = period
            self.values = tuple(values)
    observations = [
        _Obs(period=period, values=item["values"])
        for period, item in sorted(by_period.items())
    ]
    if not observations:
        raise ValueError("tdra_telecom_monthly is empty; nothing to merge")

    payload = {
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "source_label": SOURCE_NAME,
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


if __name__ == "__main__":
    print("source_tdra.py 自检：")
    print("  update(con, force=, skip_download=) 从 TDRA Open Data 目录页发现并下载 9 个")
    print("    xlsx 到 raw/tdra/，解析 'Monthly statistics' 逐月，入长表 tdra_telecom_monthly")
    print("  merge(workbook_path) 把表写回 月度_TDRA")
