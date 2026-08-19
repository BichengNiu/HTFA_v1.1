"""MEsteel 阿联酋钢材月度报价：入库与写表。

逻辑移植自 ``data/steelPrice/``（download_mesteel.py 下载 + process_mesteel.py
清洗 + merge_workbook.py 写表）。原始 JSON 缓存写入 ``data/UAE/raw/steel/``；
入库表 ``mesteel_monthly`` 的 period 为月末日期，保留报价区间下限/上限/中值与
产地标签。工作簿 sheet 为 ``月度_MEsteel``（区间中值宽表，缺报月份留空）。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from calendar import monthrange
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, NamedTuple
from urllib.request import Request, urlopen

SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db  # noqa: E402

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RAW_DIR = DATA_DIR / "raw" / "steel"
RAW_PATH = RAW_DIR / "mesteel_monthly_prices.json"
MANIFEST_PATH = RAW_DIR / "source_manifest.json"
# merge_workbook.ps1 硬编码从脚本旁 processed/ 读质量报告，路径必须一致
QUALITY_PATH = SCRIPTS_DIR / "processed" / "quality_report.json"
MERGE_SCRIPT = SCRIPTS_DIR / "merge_workbook.ps1"

TARGET_SHEET = "月度_MEsteel"
SOURCE_NAME = "MEsteel"
SOURCE_BASIS = "CFR/CPT UAE"
UNIT = "美元/吨"
SOURCE_URL = "https://mesteel.com/newsletter/get_monthly_prices.php"
LANDING_PAGE_URL = "https://mesteel.com/newsletter/monthly_prices_latest4.php"


class Product(NamedTuple):
    code: str
    english: str
    chinese: str

    @property
    def indicator_name(self) -> str:
        return f"阿联酋:钢材进口报价:{self.chinese}:CFR/CPT:区间中值"


PRODUCTS = (
    Product("billets_blooms", "Billets Blooms", "钢坯及方坯"),
    Product("reinforcing_bars", "Reinforcing Bars", "螺纹钢"),
    Product("angles", "Angles", "角钢"),
    Product("beams_jis", "Beams (JIS-Sizes)", "JIS规格型钢梁"),
    Product(
        "beams_channels_en",
        "Beams - Channels (EN + UB/UC)",
        "EN及UB/UC型钢梁和槽钢",
    ),
    Product("wire_rod", "Wire Rod", "线材"),
    Product("hot_rolled_plates", "Hot Rolled Plates", "热轧钢板"),
    Product("hot_rolled_coils_3mm", "Hot Rolled Coils, 3mm", "3mm热轧卷"),
    Product("cold_rolled_coils_1mm", "Cold Rolled Coils, 1mm", "1mm冷轧卷"),
    Product(
        "hdg_hr_2mm_275",
        "Hot Dip Galv. Coils, HR base, 2mm, 275g/m2",
        "2mm热基热镀锌卷(275g/m2)",
    ),
    Product(
        "hdg_cr_1mm_275",
        "Hot Dip Galv. Coils, CR base, 1mm, 275g/m2",
        "1mm冷基热镀锌卷(275g/m2)",
    ),
    Product(
        "prepainted_galv_035mm_90",
        "Prepainted Galv. Coils 0.35mm 90g",
        "0.35mm预涂镀锌卷(90g)",
    ),
    Product("tinplate_032mm", "Tinplate 0.32MM", "0.32mm马口铁"),
    Product(
        "stainless_hr_304",
        "Stainless HR Coils 304 base",
        "304基价不锈钢热轧卷",
    ),
    Product(
        "stainless_hr_316l",
        "Stainless HR Coils 316L base",
        "316L基价不锈钢热轧卷",
    ),
)
PRODUCT_BY_ENGLISH = {product.english: product for product in PRODUCTS}
NUMBER_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?")


# ---------------------------------------------------------------------------
# 下载器（平移自 download_mesteel.py）
# ---------------------------------------------------------------------------


def validate_payload(payload: Any) -> dict[str, Any]:
    """Validate the stable fields needed by the downstream processor."""

    if not isinstance(payload, dict):
        raise ValueError("MEsteel response must be a JSON object")
    dates = payload.get("dates")
    records = payload.get("data")
    if not isinstance(dates, list) or not dates:
        raise ValueError("MEsteel response has no dates")
    if not isinstance(records, list) or not records:
        raise ValueError("MEsteel response has no data records")
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("MEsteel dates must be sorted and unique")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"MEsteel record {index} is not an object")
        for field in ("product", "origin", "prices"):
            if field not in record:
                raise ValueError(f"MEsteel record {index} is missing {field}")
        if not isinstance(record["prices"], dict):
            raise ValueError(f"MEsteel record {index} prices must be an object")
    return payload


def download(timeout: int = 30) -> tuple[Path, Path]:
    """Download, validate, and atomically persist the current JSON payload."""

    request = Request(
        SOURCE_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "HTFA-MEsteel-data-collector/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw_bytes = response.read()
    payload = validate_payload(json.loads(raw_bytes.decode("utf-8-sig")))

    canonical_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode(
        "utf-8"
    )
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    products = sorted({record["product"] for record in payload["data"]})
    manifest = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "source_url": SOURCE_URL,
        "landing_page_url": LANDING_PAGE_URL,
        "sha256": digest,
        "date_count": len(payload["dates"]),
        "record_count": len(payload["data"]),
        "product_count": len(products),
        "products": products,
        "first_source_month": payload["dates"][0],
        "last_source_month": payload["dates"][-1],
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_temporary = RAW_PATH.with_suffix(".json.tmp")
    manifest_temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    raw_temporary.write_bytes(canonical_bytes)
    manifest_temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    raw_temporary.replace(RAW_PATH)
    manifest_temporary.replace(MANIFEST_PATH)
    return RAW_PATH, MANIFEST_PATH


# ---------------------------------------------------------------------------
# 清洗（平移自 process_mesteel.py）
# ---------------------------------------------------------------------------


def parse_quote(value: Any) -> tuple[float, float, float]:
    """Return low, high and midpoint for a scalar or range quote."""

    text = str(value).strip().replace(",", "")
    numbers = [float(item) for item in NUMBER_PATTERN.findall(text)]
    if len(numbers) == 1:
        low = high = numbers[0]
    elif len(numbers) == 2:
        low, high = numbers
    else:
        raise ValueError(f"Unsupported MEsteel quote: {value!r}")
    if low > high:
        raise ValueError(f"MEsteel quote has descending bounds: {value!r}")
    return low, high, (low + high) / 2


def month_end(source_date: str) -> date:
    """'YYYY-MM-DD'（接口月初日期）-> 该月最后一天的 date。"""

    parsed = datetime.strptime(source_date, "%Y-%m-%d").date()
    last_day = monthrange(parsed.year, parsed.month)[1]
    return date(parsed.year, parsed.month, last_day)


def load_payload(path: Path = RAW_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload.get("dates"), list):
        raise ValueError("Raw MEsteel payload has no dates list")
    if not isinstance(payload.get("data"), list):
        raise ValueError("Raw MEsteel payload has no data list")
    return payload


def clean_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Create DB rows (long), workbook wide rows and quality statistics."""

    source_products = {record["product"] for record in payload["data"]}
    segment_counts = Counter(record["product"] for record in payload["data"])
    expected_products = set(PRODUCT_BY_ENGLISH)
    unknown = sorted(source_products - expected_products)
    missing = sorted(expected_products - source_products)
    if unknown or missing:
        raise ValueError(
            "MEsteel product catalogue changed; "
            f"unknown={unknown}, missing={missing}"
        )

    long_rows: list[dict[str, Any]] = []
    values_by_month: dict[date, dict[str, float]] = defaultdict(dict)
    seen_product_month: set[tuple[str, str]] = set()
    coverage: dict[str, dict[str, Any]] = {}

    for record in payload["data"]:
        product = PRODUCT_BY_ENGLISH[record["product"]]
        origin = str(record["origin"]).strip()
        for source_month, raw_quote in record["prices"].items():
            if raw_quote in (None, "", "-"):
                continue
            key = (product.code, source_month)
            if key in seen_product_month:
                raise ValueError(
                    "Overlapping MEsteel origin segments for "
                    f"{product.english} in {source_month}"
                )
            seen_product_month.add(key)
            low, high, midpoint = parse_quote(raw_quote)
            period_end = month_end(source_month)
            values_by_month[period_end][product.indicator_name] = midpoint
            long_rows.append(
                {
                    "period": period_end,
                    "product": product.chinese,
                    "product_code": product.code,
                    "product_en": product.english,
                    "origin": origin,
                    "quote_text": str(raw_quote).strip(),
                    "low": low,
                    "high": high,
                    "midpoint": midpoint,
                }
            )

    long_rows.sort(key=lambda row: (row["period"], row["product_code"]))
    wide_rows = []
    for period_end in sorted(values_by_month, reverse=True):
        row: dict[str, Any] = {"month_end": period_end.isoformat()}
        for product in PRODUCTS:
            row[product.indicator_name] = values_by_month[period_end].get(
                product.indicator_name
            )
        wide_rows.append(row)

    for product in PRODUCTS:
        rows = [row for row in long_rows if row["product_code"] == product.code]
        coverage[product.code] = {
            "product_en": product.english,
            "product_zh": product.chinese,
            "indicator_name": product.indicator_name,
            "observation_count": len(rows),
            "first_month": rows[0]["period"].isoformat(),
            "last_month": rows[-1]["period"].isoformat(),
            "origin_segment_count": segment_counts[product.english],
        }

    quality = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": SOURCE_NAME,
        "basis": SOURCE_BASIS,
        "workbook_unit": UNIT,
        "raw_date_count": len(payload["dates"]),
        "raw_record_count": len(payload["data"]),
        "product_count": len(PRODUCTS),
        "long_row_count": len(long_rows),
        "wide_row_count": len(wide_rows),
        "first_month": min(row["period"].isoformat() for row in long_rows),
        "last_month": max(row["period"].isoformat() for row in long_rows),
        "overlapping_product_month_count": 0,
        "unparsed_quote_count": 0,
        "coverage": coverage,
    }
    return long_rows, wide_rows, quality


# ---------------------------------------------------------------------------
# 入库与写表
# ---------------------------------------------------------------------------


def _dictionary_rows() -> list[dict]:
    return [
        {
            "indicator_name": product.indicator_name,
            "frequency": "月",
            "unit": UNIT,
            "source": SOURCE_NAME,
            "type": "价格",
            "industry": "钢铁",
            "updated_at": date.today(),
        }
        for product in PRODUCTS
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


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def update(con, *, force: bool = False, skip_download: bool = False) -> dict:
    """下载（按需）→ 清洗 → 事务内入库 mesteel_monthly。"""

    if skip_download:
        if not RAW_PATH.is_file():
            raise FileNotFoundError(
                f"--skip-download 但缺少缓存: {RAW_PATH}"
            )
    elif force or not RAW_PATH.is_file():
        download()

    payload = load_payload(RAW_PATH)
    long_rows, wide_rows, quality = clean_payload(payload)
    quality["raw_sha256"] = hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()
    _atomic_json(QUALITY_PATH, quality)

    rows = [
        {
            "period": row["period"],
            "product": row["product"],
            "lower": row["low"],
            "upper": row["high"],
            "midpoint": row["midpoint"],
            "origin_label": row["origin"],
        }
        for row in long_rows
    ]
    with _transaction(con):
        db.replace(con, "mesteel_monthly", rows)
        db.upsert_dictionary_rows(con, _dictionary_rows())

    note = (
        f"{len(rows)} 条报价（{quality['first_month']} 至 {quality['last_month']}），"
        f"{quality['product_count']} 个产品"
    )
    return {"status": "ok", "rows": len(rows), "note": note}


def _build_wide_csv(con) -> Path:
    """从库构建与旧 processed/mesteel_monthly_midpoint_wide.csv 同构的 CSV。"""

    rows = con.execute(
        "SELECT period, product, midpoint FROM mesteel_monthly"
    ).fetchall()
    values_by_month: dict[date, dict[str, float | None]] = defaultdict(dict)
    for period, product, midpoint in rows:
        values_by_month[period][product] = midpoint
    wide_fields = ["month_end"] + [
        product.indicator_name for product in PRODUCTS
    ]
    wide_rows = []
    for period_end in sorted(values_by_month, reverse=True):
        row: dict[str, Any] = {"month_end": period_end.isoformat()}
        for product in PRODUCTS:
            row[product.indicator_name] = values_by_month[period_end].get(
                product.chinese
            )
        wide_rows.append(row)

    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=".mesteel-wide-", suffix=".csv", dir=DATA_DIR
    )
    os.close(temporary_fd)
    temporary = Path(temporary_name)
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=wide_fields)
        writer.writeheader()
        writer.writerows(wide_rows)
    return temporary


def merge(workbook_path: Path) -> dict:
    """把 mesteel_monthly 中值宽表合并进 月度_MEsteel sheet。"""

    workbook_path = workbook_path.resolve()
    lock_path = workbook_path.with_name(f"~${workbook_path.name}")
    if lock_path.exists():
        raise PermissionError(
            f"Close Excel before updating the workbook: {lock_path}"
        )
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Destination workbook not found: {workbook_path}")
    if not MERGE_SCRIPT.is_file():
        raise FileNotFoundError(f"Excel merge helper not found: {MERGE_SCRIPT}")

    con = db.connect(read_only=True)
    try:
        wide_path = _build_wide_csv(con)
    finally:
        con.close()
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(MERGE_SCRIPT),
                "-WorkbookPath",
                str(workbook_path),
                "-WideCsvPath",
                str(wide_path),
            ],
            check=False,
            cwd=DATA_DIR,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Excel merge did not complete successfully: "
                f"{completed.stderr or completed.stdout}"
            )
    finally:
        wide_path.unlink(missing_ok=True)
    return {"status": "ok", "note": f"{TARGET_SHEET} 已更新"}


if __name__ == "__main__":
    print("source_steel: 模块入口由 data/UAE/update_data.py 与 data/UAE/merge_workbook.py 调用")
