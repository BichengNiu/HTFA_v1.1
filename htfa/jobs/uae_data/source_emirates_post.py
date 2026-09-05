"""Emirates Post 国内邮政服务量（Domestic Postal Services Volume）入库与写表。

数据来源：bayanat.ae（阿联酋联邦官方开放数据门户）数据集「Domestic Postal
Services Volume」，由 Emirates Post Group 发布（源站
https://www.emiratespost.ae/open-data，开放数据分类 Postal Services /
Postal Market / Postal Shipments / Domestic）。数据集标识
Domestic_Volume_2022_2025：月度、按 寄出城市 × 寄达城市 × 服务类型 拆分的
国内邮政发运件数，覆盖 2022-01 至 2025-12、全部 7 个酋长国（7 类服务，
原始文件 3 个 sheet：Metadata / Data Dictionary / Dataset，明细 6001 行）。

下载：门户数据集信息页公开提供「Download」按钮，实际文件来自
    GET /api/DatasetResources/DownloadSingle?resourceID={rid}&fileName={name}
无需登录或密钥。资源 ID 与文件名从信息页 HTML 中解析（button#resourceDownload
的 data-resource-id / data-file-name），解析失败时回退到硬编码常量（当前
数据集，经 2026-08-18 实抓核验）。原始文件保存到 raw/emirates_post/。

流程与 source_cbuae.py 一致：``update()`` 下载（或复用 raw/ 现有文件）→
解析 xlsx → 与期望值校验（表头、年份集合、服务集合、非负整数，fail loud
防解析漂移）→ 入明细表 ``emirates_post_monthly``（(period, origin_city,
destn_city, service) 粒度）；``merge()`` 从库按 (period, service) 聚合全国
月度总量与 7 类服务分解，调用 ``write_emirates_post_sheet.ps1`` 重建 Excel
「月度_邮政」sheet 并同步「指标字典」。城市对维度保留在库内明细表，Excel
不展开（7×7 组合 × 48 月过大）；缺失值以 ``None`` 写入并留空单元格，不臆造。
"""

from __future__ import annotations

import collections
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import quote

from .paths import DATA_DIR, SCRIPTS_DIR


from . import db  # noqa: E402
from ._excel_helpers import (  # noqa: E402
    payload_json_file,
    records_latest_first,
    run_powershell_sheet_writer,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "emirates_post"
RAW_FILE_NAME = "emirates_post_domestic_postal_services_volume.xlsx"
TARGET_SHEET = "月度_邮政"
DICTIONARY_SHEET = "指标字典"
SOURCE_NAME = "Emirates Post (bayanat.ae)"
UNIT = "件"
INDUSTRY = "邮政物流"
FREQUENCY = "月"

# 数据集信息页（bayanat.ae 门户，服务端渲染，HTML 内嵌资源标识）
DATASET_PAGE_URL = (
    "https://bayanat.ae/Datasets/Dataset-info"
    "?id=xXwKgwMkhnTL7sJ5gg65jw-d4lvgRFJJZ2z2Fj7YRts"
)
DOWNLOAD_API = "https://bayanat.ae/api/DatasetResources/DownloadSingle"
# 回退常量：2026-08-18 实抓页面的当前资源
FALLBACK_RESOURCE_ID = "gIGxt-bcrjfBlNRrxFRKBWl9zRilVz9ZEbXpws2UY2Q"
FALLBACK_FILE_NAME = "Domestic Postal Services Volume"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": DATASET_PAGE_URL,
}

EXPECTED_DATASET_NAME = "Domestic Postal Services Volume"
EXPECTED_HEADER = (
    "YEAR", "MONTHNAME", "ORIGIN_CITY", "DESTN_CITY", "SERVICE", "VOLUME",
)
# 服务类型集合（跨月稳定）；出现变化时 fail loud 提示人工复核后更新
EXPECTED_SERVICES = frozenset(
    {
        "Emirates ID",
        "Express Mail",
        "Flat Rate",
        "Parcel Delivery",
        "Registered Mail",
        "Parcel",
        "EMS",
    }
)
# 期望年份集合；新年度进入数据集时 fail loud 提示人工复核后更新
EXPECTED_YEARS = frozenset({2022, 2023, 2024, 2025})

# 指标（Excel 宽表列序）：全国月度总量 + 7 类服务分解
TOTAL_INDICATOR = "阿联酋:国内邮政服务量(总件数)"
SERVICE_INDICATOR_TMPL = "阿联酋:国内邮政服务量({service})"
# (列序, 指标名, 指标字典 type)
INDICATORS = [(TOTAL_INDICATOR, "总量")] + [
    (SERVICE_INDICATOR_TMPL.format(service=service), "服务细分")
    for service in sorted(EXPECTED_SERVICES)
]
INDICATOR_ORDER = {
    name: index for index, (name, _) in enumerate(INDICATORS)
}
SERVICE_ORDER = {service: i + 1 for i, service in enumerate(sorted(EXPECTED_SERVICES))}

MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------


def _fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _discover_resource() -> tuple[str, str]:
    """从数据集信息页解析当前资源 (resourceID, fileName)。

    失败时回退到 FALLBACK_* 常量并返回提示，不阻断下载（资源 ID 长期稳定）。
    """
    try:
        html = _fetch_bytes(DATASET_PAGE_URL).decode("utf-8", errors="replace")
    except Exception:
        return FALLBACK_RESOURCE_ID, FALLBACK_FILE_NAME
    match = re.search(
        r'id="resourceDownload"\s+data-resource-id="([^"]+)"\s+'
        r'data-file-name="([^"]+)"',
        html,
    )
    if match:
        return match.group(1), match.group(2)
    return FALLBACK_RESOURCE_ID, FALLBACK_FILE_NAME


def download(force: bool = False) -> Path:
    """下载最新 xlsx 到 raw/emirates_post/（force=False 且已存在时复用）。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / RAW_FILE_NAME
    if target.is_file() and not force:
        return target
    resource_id, file_name = _discover_resource()
    url = f"{DOWNLOAD_API}?resourceID={resource_id}&fileName={quote(file_name)}"
    payload = _fetch_bytes(url)
    if not payload.startswith(b"PK"):
        raise ValueError(
            f"bayanat 下载响应不是 xlsx 文件（{len(payload)} 字节，"
            f"开头 {payload[:8]!r}）"
        )
    target.write_bytes(payload)
    return target


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def _load_raw_workbook(path: Path) -> "openpyxl.workbook.Workbook":
    import openpyxl

    return openpyxl.load_workbook(path, read_only=True, data_only=True)


def _metadata_value(metadata_rows: list[list], column: str) -> str | None:
    for row in metadata_rows:
        if row and str(row[0]).strip() == column:
            value = row[1] if len(row) > 1 else None
            return None if value is None else str(value).strip()
    return None


def _row_to_int(value) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"VOLUME 非法值: {value!r}")
    number = float(value)
    if number != int(number) or number < 0:
        raise ValueError(f"VOLUME 非法值: {value!r}")
    return int(number)


def parse_workbook(path: Path) -> tuple[list[dict], dict, dict]:
    """解析 xlsx 原始文件：返回 (聚合行列表, 元数据, 重复统计)。

    源文件同一 (期间, 城市对, 服务) 可能出现多行（经核验为 2025-03 至
    2025-11 的 Express Mail，每月约 30 个城市对两版数值并存，属源发布
    质量问题）：解析时按同键 **求和** 去重入库（信息不丢、幂等），并用
    raw_rows 记录源行数以便审计。全部校验失败即抛错（fail loud），防止
    源格式/口径漂移导致静默错数。
    """
    workbook = _load_raw_workbook(path)
    try:
        sheet_names = workbook.sheetnames
        if "Dataset" not in sheet_names or "Metadata" not in sheet_names:
            raise ValueError(
                f"源 xlsx sheet 结构异常: {sheet_names}（期望含 Metadata/Dataset）"
            )

        metadata_rows = list(
            workbook["Metadata"].iter_rows(values_only=True)
        )
        dataset_name = _metadata_value(metadata_rows, "Dataset Name_EN")
        if dataset_name != EXPECTED_DATASET_NAME:
            raise ValueError(
                f"源数据集名不符: {dataset_name!r}（期望 {EXPECTED_DATASET_NAME!r}）"
            )
        metadata = {
            "dataset_identifier": _metadata_value(
                metadata_rows, "Dataset Identifier"
            ),
            "source_url": _metadata_value(metadata_rows, "Source (URL)"),
            "last_update": _metadata_value(
                metadata_rows, "Last Update Date YYYY-MM-DD"
            ),
        }

        raw_rows: list[dict] = []
        years: set[int] = set()
        services: set[str] = set()
        row_index = 0
        for row in workbook["Dataset"].iter_rows(values_only=True):
            if row_index == 0:
                if tuple(row) != EXPECTED_HEADER:
                    raise ValueError(
                        f"Dataset 表头不符: {row!r}（期望 {EXPECTED_HEADER!r}）"
                    )
                row_index += 1
                continue
            year, month_name, origin, destn, service, volume = row
            if origin is None:
                origin = ""  # 源数据个别行缺出发城市（2024-10 有 1 行），保留为 ''
            if destn is None:
                destn = ""
            if service is None:
                raise ValueError(f"行 {row_index}: SERVICE 为空")
            month = MONTH_NUMBERS.get(str(month_name).strip().lower()[:3])
            if month is None:
                raise ValueError(f"行 {row_index}: 月份非法 {month_name!r}")
            raw_rows.append(
                {
                    "period": (year, month),
                    "origin_city": str(origin).strip(),
                    "destn_city": str(destn).strip(),
                    "service": str(service).strip(),
                    "volume": _row_to_int(volume),
                }
            )
            years.add(year)
            services.add(str(service).strip())
            row_index += 1

        if years != EXPECTED_YEARS:
            raise ValueError(
                f"年份集合与期望不符: {sorted(years)}（期望 "
                f"{sorted(EXPECTED_YEARS)}）。如源站已发布新年度数据，"
                f"请人工核验后同步更新 source_emirates_post.py 的 EXPECTED_YEARS"
            )
        if services != EXPECTED_SERVICES:
            raise ValueError(
                f"服务类型集合与期望不符: {sorted(services)}（期望 "
                f"{sorted(EXPECTED_SERVICES)}）。如源站调整服务分类，请人工核验后"
                f"同步更新 EXPECTED_SERVICES 与 INDICATORS"
            )
        if len(raw_rows) < 5000:
            raise ValueError(f"明细行数异常偏少: {len(raw_rows)} 行")

        # 同键聚合：volume 求和，raw_rows 记源文件行数
        buckets: dict[tuple, dict] = {}
        for item in raw_rows:
            key = (
                item["period"][0],
                item["period"][1],
                item["origin_city"],
                item["destn_city"],
                item["service"],
            )
            bucket = buckets.setdefault(
                key,
                {
                    "period": date(item["period"][0], item["period"][1], 1),
                    "origin_city": item["origin_city"],
                    "destn_city": item["destn_city"],
                    "service": item["service"],
                    "volume": 0,
                    "raw_rows": 0,
                },
            )
            bucket["volume"] += item["volume"]
            bucket["raw_rows"] += 1

        rows = list(buckets.values())
        # 同键重复的分布（按 年-月-服务），供 update() 记入警告
        dup_by_year_month = collections.Counter(
            (
                r["period"].year,
                r["period"].month,
                r["service"],
            )
            for r in rows
            if r["raw_rows"] > 1
        )
        duplicate_stats = {
            "dup_groups": sum(1 for r in rows if r["raw_rows"] > 1),
            "dup_by_year_month": dict(dup_by_year_month),
        }
        return rows, metadata, duplicate_stats
    finally:
        workbook.close()


# ---------------------------------------------------------------------------
# 入库 / 写表
# ---------------------------------------------------------------------------


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": name,
            "frequency": FREQUENCY,
            "unit": UNIT,
            "source": SOURCE_NAME,
            "type": indicator_type,
            "industry": INDUSTRY,
            "updated_at": date.today(),
        }
        for name, indicator_type in INDICATORS
    ]


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载（或复用 raw/ 现有文件）→ 解析校验 → 入 detail.emirates_post_monthly。

    校验通过才入库；明细粒度 (period, origin_city, destn_city, service)，
    共 6001 行（2022-01 至 2025-12）。``skip_download`` 时不访问网络。
    """
    if skip_download and not (RAW_DIR / RAW_FILE_NAME).is_file():
        raise ValueError(
            f"--skip-download 模式下缺少原始文件: {RAW_DIR / RAW_FILE_NAME}"
        )
    path = download(force=force) if not skip_download else RAW_DIR / RAW_FILE_NAME
    rows, metadata, duplicate_stats = parse_workbook(path)

    con.begin()
    try:
        db.replace(con, "emirates_post_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())
        con.commit()
    except Exception:
        con.rollback()
        raise

    periods = sorted({row["period"].strftime("%Y-%m") for row in rows})
    note = (
        f"{len(rows)} 行明细（源文件 {sum(r['raw_rows'] for r in rows)} 行，"
        f"{periods[0]} 至 {periods[-1]}，7 城市 × 7 服务）；数据集标识 "
        f"{metadata.get('dataset_identifier')}；来源页 "
        f"{metadata.get('source_url') or '（未注明）'}"
    )
    if duplicate_stats["dup_groups"]:
        sample = sorted(duplicate_stats["dup_by_year_month"])[:3]
        note += (
            f"；⚠ 源文件 {duplicate_stats['dup_groups']} 组同键重复"
            f"（如 {sample}），已按同键求和入库并记 raw_rows"
        )
    return {"status": "ok", "rows": len(rows), "note": note}


def _aggregate_rows(db_rows: list[tuple]) -> dict[str, dict]:
    """库内明细 → {period: {values: [总量, 7 服务...], } }。"""
    totals: dict[str, int] = {}
    by_service: dict[str, dict[str, int]] = {}
    for period, service, volume in db_rows:
        key = period.strftime("%Y-%m")
        totals[key] = totals.get(key, 0) + (volume or 0)
        by_service.setdefault(service, {})[key] = volume
    by_period: dict[str, dict] = {}
    for key in sorted(totals):
        values = [None] * len(INDICATORS)
        values[INDICATOR_ORDER[TOTAL_INDICATOR]] = totals[key]
        for service, service_map in by_service.items():
            values[SERVICE_ORDER[service]] = service_map.get(key)
        by_period[key] = {"values": values}
    return by_period


def merge(workbook_path: Path) -> dict:
    """把 emirates_post_monthly 聚合写回 阿联酋.xlsx 的 月度_邮政 sheet。

    从库中按 (period, service) 聚合出全国月度总量与 7 类服务分解，还原成
    period × 指标 宽表（最新在前）；某月某服务源数据缺行时该单元格留空。
    """

    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    helper_path = Path(__file__).with_name("write_emirates_post_sheet.ps1")
    if not helper_path.is_file():
        raise FileNotFoundError(f"Excel writer helper not found: {helper_path}")

    con = db.connect(read_only=True)
    try:
        db_rows = con.execute(
            "SELECT period, service, SUM(volume) AS volume "
            "FROM detail.emirates_post_monthly "
            "GROUP BY period, service ORDER BY period"
        ).fetchall()
    finally:
        con.close()
    if not db_rows:
        raise ValueError("emirates_post_monthly is empty; nothing to merge")

    by_period = _aggregate_rows(db_rows)
    observations = [
        type(
            "Observation",
            (),
            {
                "period": period,
                "values": tuple(item["values"]),
                "source_file": RAW_FILE_NAME,
            },
        )()
        for period, item in sorted(by_period.items())
    ]

    payload = {
        "source_label": SOURCE_NAME,
        "legacy_sheet_names": [],
        "dictionary_sheet_name": DICTIONARY_SHEET,
        "metadata_labels": ["指标名称", "频率", "单位", "来源", "更新时间"],
        "frequency": FREQUENCY,
        "unit": UNIT,
        "source": SOURCE_NAME,
        "updated_at": date.today().isoformat(),
        "indicators": [
            {"name": name, "type": indicator_type, "industry": INDUSTRY, "unit": UNIT}
            for name, indicator_type in INDICATORS
        ],
        "records": records_latest_first(observations),
    }
    with payload_json_file(
        payload,
        prefix=".emirates-post-sheet-",
        directory=DATA_DIR,
    ) as payload_path:
        run_powershell_sheet_writer(
            helper_path, workbook_path, payload_path, TARGET_SHEET
        )
    return {
        "status": "ok",
        "note": f"{len(observations)} 个月写入 {TARGET_SHEET}"
        f"（{len(INDICATORS)} 个指标）",
    }


if __name__ == "__main__":
    print("source_emirates_post.py 自检：")
    print("  update(con, force=, skip_download=) 下载/解析 bayanat.ae 的")
    print("    Domestic Postal Services Volume xlsx → 校验 → 入明细表 "
          "emirates_post_monthly")
    print("  merge(workbook_path) 按 (period, service) 聚合 → 写回 月度_邮政")
    print("  本文件直接运行不执行任何下载或工作簿写入。")
